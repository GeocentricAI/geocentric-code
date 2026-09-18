"""Slash commands for the interactive REPL."""
from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import session as session_mod
from . import tools as tools_mod
from .config import EFFORT_LEVELS, _guess_param_size_b, commands_dir
from .permissions import Decision
from .tools.shell import JOBS
from .tools.todo import STORE as TODO_STORE
from .ui.banner import render_banner
from .ui.diff import render_diff
from .ui.render import context_meter, render_todos

HELP_SECTIONS = [
    ("session", [
        ("/help", "show this help"),
        ("/clear", "start a fresh conversation"),
        ("/compact", "summarize history to free context"),
        ("/context", "context usage; /context set <n> or reset"),
        ("/theme", "change the color theme"),
        ("/resume [id]", "reload a previous session"),
        ("/sessions", "list recent sessions"),
        ("/export [file]", "write this session to markdown"),
        ("/stats", "tokens, tools, files touched"),
        ("/quit", "leave geocentric"),
    ]),
    ("model", [
        ("/model [name]", "show or switch the active model"),
        ("/models", "list models pulled in Ollama"),
        ("/effort [level]", "thinking budget: " + " → ".join(EFFORT_LEVELS)),
    ]),
    ("work", [
        ("/plan", "read-only planning mode — investigate, then propose"),
        ("/accept", "leave plan mode and execute the plan"),
        ("/todos", "show the current task list"),
        ("/diff", "git diff of the working tree"),
        ("/undo", "revert the last file edit geocentric made"),
        ("/review", "review uncommitted changes"),
        ("/test", "find and run the project's tests"),
        ("/commit [msg]", "stage everything and commit"),
        ("/init", "write a GEOCENTRIC.md briefing for this project"),
    ]),
    ("control", [
        ("/tools", "list tools the agent can call"),
        ("/jobs", "background jobs"),
        ("/permissions", "toggle auto-accept (or press shift+tab)"),
        ("/approve /deny /always", "answer a pending approval"),
        ("/answer <n>", "answer a question the agent asked"),
        ("/add <path>", "paste a file into the conversation"),
        ("/system", "print the current system prompt"),
    ]),
]

BUILTIN_NAMES = [
    "/help", "/clear", "/compact", "/context", "/resume", "/sessions", "/export", "/stats",
    "/quit", "/exit", "/model", "/models", "/effort", "/plan", "/accept", "/todos", "/diff",
    "/undo", "/review", "/test", "/commit", "/init", "/tools", "/jobs", "/permissions",
    "/yolo", "/approve", "/deny", "/always", "/answer", "/add", "/system", "/banner", "/theme",
]

# Commands that mutate agent state and would race a turn running on the worker thread.
UNSAFE_WHILE_BUSY = {"/clear", "/compact", "/undo", "/init", "/resume", "/model", "/plan", "/accept"}


@dataclass
class CommandResult:
    quit: bool = False
    submit: str = ""  # text to send to the model as if the user typed it


# name -> one-line description, derived from the help table so the two can't drift apart.
COMMAND_META = {}
for _section, _entries in HELP_SECTIONS:
    for _name, _desc in _entries:
        for _alias in _name.split(" ")[0].split("|"):
            COMMAND_META[_alias.strip()] = _desc
COMMAND_META.setdefault("/exit", "leave geocentric")
COMMAND_META.setdefault("/yolo", "toggle auto-accept")
COMMAND_META.setdefault("/banner", "replay the intro banner")
COMMAND_META.setdefault("/approve", "approve the pending tool call")
COMMAND_META.setdefault("/answer", "answer the agent's pending question")
COMMAND_META.setdefault("/deny", "deny the pending tool call")
COMMAND_META.setdefault("/always", "allow this tool for the rest of the session")


def argument_options(cmd: str, ctx) -> list:
    """Completion candidates for a command's argument, as (value, description) pairs.

    Returning [] means "no fixed set" - the completer falls back to path completion for
    the commands that take one, and offers nothing for free-text commands.
    """
    if cmd == "/effort":
        blurbs = {
            "low": "fastest, no thinking",
            "medium": "balanced (default)",
            "high": "thinks before answering",
            "xhigh": "explores alternatives",
            "max": "verifies with tools",
            "ultracode": "exhaustive, slowest",
        }
        return [(lvl, blurbs.get(lvl, "")) for lvl in EFFORT_LEVELS]

    if cmd == "/model":
        try:
            models = ctx.client.list_models()
        except Exception:
            return []
        out = []
        for m in sorted(models, key=lambda x: x.get("name", "")):
            name = m.get("name") or m.get("model")
            size = m.get("size", 0) / (1024 ** 3)
            marker = "● current · " if name == ctx.model else ""
            out.append((name, f"{marker}{size:.1f}GB"))
        return out

    if cmd in ("/permissions", "/yolo"):
        return [("on", "auto-approve tool calls"), ("off", "ask before mutating actions")]

    if cmd == "/answer":
        runner = getattr(ctx, "runner", None)
        pending = runner.pending_question if runner else None
        if not pending:
            return []
        return [(str(i), o["label"] + (f" — {o['description']}" if o.get("description") else ""))
                for i, o in enumerate(pending["options"], 1)]

    if cmd == "/diff":
        return [("staged", "show the staged diff instead")]

    if cmd == "/theme":
        from .ui.theme import theme_options
        return [(n, d + ("  ← current" if n == ctx.config.theme else "")) for n, d in theme_options()]

    if cmd == "/context":
        opts = [("reset", "back to the automatic window")]
        model_max = 0
        try:
            model_max = ctx.agent.model_max_context()
        except Exception:
            pass
        for n in (8192, 16384, 32768, 65536, 131072):
            if not model_max or n <= model_max:
                note = "more GPU memory" if n > 16384 else "modest memory use"
                opts.append((f"set {n}", f"{n // 1024}k tokens · {note}"))
        return opts

    if cmd == "/resume":
        try:
            return [(m.id, f"{m.age} · {m.turns} turns · {m.title(40)}")
                    for m in session_mod.list_sessions(ctx.cwd, limit=15)]
        except Exception:
            return []

    if cmd == "/jobs":
        opts = [("kill all", "stop every background job")]
        try:
            opts += [(f"kill {j.id}", ("running · " if j.running else "exited · ") + j.command[:40])
                     for j in JOBS.all()]
        except Exception:
            pass
        return opts

    if cmd == "/test":
        found = []
        for name, cmd_hint in [("pytest.ini", "pytest"), ("pyproject.toml", "pytest"),
                               ("package.json", "npm test"), ("Cargo.toml", "cargo test"),
                               ("go.mod", "go test ./..."), ("Makefile", "make test")]:
            if (ctx.cwd / name).exists() and cmd_hint not in [f[0] for f in found]:
                found.append((cmd_hint, f"detected from {name}"))
        return found

    return []


# Commands whose argument is a filesystem path.
PATH_ARG_COMMANDS = {"/add", "/export"}


def load_custom_commands(root: Path) -> dict:
    """Load user-defined commands from .geocentric/commands/*.md.

    Each file becomes /<filename>. The body is a prompt template; $ARGUMENTS is replaced
    with whatever the user typed after the command. This is the cheapest possible way to
    let someone codify "review this the way my team reviews things" once and reuse it.
    """
    out = {}
    d = commands_dir(root)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.md")):
        try:
            body = p.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if body:
            out[f"/{p.stem}"] = body
    return out


def all_command_names(custom: dict) -> list:
    return sorted(set(BUILTIN_NAMES) | set(custom))


def handle(line: str, ctx) -> CommandResult:
    console = ctx.console
    parts = line.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/quit", "/exit"):
        return CommandResult(quit=True)

    custom = getattr(ctx, "custom_commands", {}) or {}
    if cmd in custom:
        template = custom[cmd]
        return CommandResult(submit=template.replace("$ARGUMENTS", arg).strip())

    runner = getattr(ctx, "runner", None)
    if runner is not None and runner.busy.is_set() and cmd in UNSAFE_WHILE_BUSY:
        console.print(Text(f"  {cmd} needs the agent idle — ^C to interrupt, or wait.", style="warn"))
        return CommandResult()

    handler = _HANDLERS.get(cmd)
    if handler is None:
        near = [n for n in all_command_names(custom) if n.startswith(cmd[:3])][:4]
        hint = f" Did you mean {', '.join(near)}?" if near else " Try /help."
        console.print(Text(f"  unknown command {cmd!r}.{hint}", style="tool.err"))
        return CommandResult()
    return handler(ctx, arg) or CommandResult()


# ------------------------------------------------------------------------------ helpers

def _table(*columns):
    t = Table(show_header=True, header_style="tool", border_style="rule", box=None, padding=(0, 2))
    for c in columns:
        t.add_column(c)
    return t


# ----------------------------------------------------------------------------- handlers

def _help(ctx, arg):
    console = ctx.console
    console.print()
    for section, entries in HELP_SECTIONS:
        console.print(Text(f"  {section}", style="brand"))
        for name, desc in entries:
            console.print(Text(f"    {name:<26}", style="prompt") + Text(desc, style="muted"))
        console.print()
    custom = getattr(ctx, "custom_commands", {}) or {}
    if custom:
        console.print(Text("  custom  ", style="brand") + Text("(.geocentric/commands/)", style="dim"))
        for name in sorted(custom):
            first = custom[name].splitlines()[0][:60]
            console.print(Text(f"    {name:<26}", style="prompt") + Text(first, style="muted"))
        console.print()
    console.print(Text("  @path in a message attaches that file · ^C interrupts · shift+tab auto-accept", style="dim"))


def _banner(ctx, arg):
    render_banner(
        ctx.console, model=ctx.model, host=ctx.client.host, cwd=ctx.cwd,
        context_window=ctx.agent.context_window(), tool_count=len(tools_mod.TOOLS),
        project_context=ctx.agent.project_context.describe() if not ctx.agent.project_context.is_empty else "",
        git_branch=ctx.agent._git_branch(),
    )


def _system(ctx, arg):
    ctx.console.print(Panel(Text(ctx.agent._system_prompt(), style="dim"),
                            border_style="rule", title="[brand]system prompt[/brand]", title_align="left"))


def _clear(ctx, arg):
    ctx.agent.reset()
    ctx.session = ctx.new_session()
    ctx.console.print(Text("  fresh conversation.", style="muted"))


def _compact(ctx, arg):
    before = ctx.agent.refresh_budget().percent
    with ctx.console.status("  summarizing…", spinner="dots"):
        ok = ctx.agent.compact()
    if ok:
        after = ctx.agent.refresh_budget().percent
        ctx.console.print(Text(f"  compacted: {before}% → {after}% of context", style="tool.ok"))
    else:
        ctx.console.print(Text("  nothing to compact.", style="muted"))


def _context(ctx, arg):
    agent = ctx.agent
    console = ctx.console
    controller = getattr(ctx, "context_controller", None)

    parts = arg.split()
    if parts and controller:
        verb = parts[0].lower()
        if verb == "reset":
            console.print(Text(f"  context window reset to automatic ({controller.reset():,} tokens)",
                               style="tool.ok"))
            return
        if verb == "set":
            if len(parts) < 2:
                console.print(Text("  usage: /context set <tokens>   e.g. /context set 32768", style="tool.err"))
                return
            try:
                tokens = int(parts[1].replace("k", "000").replace("K", "000"))
            except ValueError:
                console.print(Text(f"  {parts[1]!r} isn't a number of tokens.", style="tool.err"))
                return
            ok, message, applied = controller.set(tokens)
            if not ok:
                console.print(Text(f"  {message}", style="tool.err"))
                return
            console.print(Text(f"  context window set to {applied:,} tokens", style="tool.ok") +
                          Text(f"  {message}", style="dim"))
            return

    budget = agent.refresh_budget()
    console.print()
    console.print(Text("  context  ", style="brand") + context_meter(budget) +
                  Text(f"  {budget.used:,} / {budget.window:,} tokens ({budget.percent}%)", style="muted"))

    model_max = agent.model_max_context()
    if model_max and model_max > budget.window:
        console.print(Text(
            f"  {ctx.model} supports {model_max:,}, but Ollama only uses its own default "
            f"unless asked — geocentric requests {budget.window:,}.",
            style="dim",
        ))
        console.print(Text('  raise it with "context_tokens": 32768 in ~/.geocentric/config.json '
                           "(uses more VRAM)", style="dim"))
    t = _table("role", "count", "approx tokens")
    from .context import estimate_tokens
    by_role = {}
    for m in agent.messages:
        role = m.get("role", "?")
        n, tok = by_role.get(role, (0, 0))
        by_role[role] = (n + 1, tok + estimate_tokens(m.get("content") or ""))
    for role, (n, tok) in by_role.items():
        t.add_row(role, str(n), f"{tok:,}")
    console.print(t)
    if not agent.project_context.is_empty:
        console.print(Text(f"  project context: {agent.project_context.describe()}", style="tool.ok"))
    from .tools.fs import REGISTRY
    console.print(Text(f"  files read this session: {REGISTRY.count()}", style="muted"))


def _tools(ctx, arg):
    t = _table("tool", "risk", "what it does")
    for group in ("read", "edit", "shell", "git", "web", "peer", "task", "general"):
        specs = [s for s in tools_mod.all_specs() if s.group == group]
        if not specs:
            continue
        t.add_row(Text(group.upper(), style="brand"), "", "")
        for s in specs:
            risk = {"low": "", "medium": "◐", "high": "●"}.get(s.danger, "")
            par = " ⇉" if s.concurrent_safe else ""
            t.add_row(f"  {s.name}{par}", risk, s.description.split(". ")[0][:70])
    ctx.console.print(t)
    ctx.console.print(Text("  ⇉ runs in parallel with other reads · ◐ ● need approval", style="dim"))


def _models(ctx, arg):
    try:
        models = ctx.client.list_models()
    except Exception as e:
        ctx.console.print(Text(f"  couldn't list models: {e}", style="tool.err"))
        return
    t = _table("model", "size", "params", "tools", "think")
    for m in sorted(models, key=lambda x: x.get("name", "")):
        name = m.get("name") or m.get("model")
        size = m.get("size", 0)
        try:
            caps = ctx.client.get_capabilities(name)
        except Exception:
            caps = []
        t.add_row(
            Text(name + (" ●" if name == ctx.model else ""), style="orbit" if name == ctx.model else "assistant"),
            f"{size / (1024 ** 3):.1f}GB",
            f"~{_guess_param_size_b(name, size):g}B",
            "✓" if "tools" in caps else "—",
            "✓" if "thinking" in caps else "—",
        )
    ctx.console.print(t)


def _model(ctx, arg):
    console = ctx.console
    if not arg:
        console.print(Text(f"  current model: {ctx.model}", style="orbit"))
        console.print(Text(f"  context window: {ctx.agent.context_window():,} tokens", style="muted"))
        console.print(Text("  usage: /model <name>   (see /models)", style="muted"))
        return
    try:
        names = [m.get("name") or m.get("model") for m in ctx.client.list_models()]
    except Exception as e:
        console.print(Text(f"  couldn't reach ollama: {e}", style="tool.err"))
        return
    match = next((n for n in names if n == arg), None) or next(
        (n for n in names if arg.lower() in n.lower()), None)
    if not match:
        console.print(Text(f"  no local model matches {arg!r}. try /models.", style="tool.err"))
        return
    ctx.model = match
    ctx.agent.set_model(match)
    ctx.config.model = match
    ctx.config.save()
    caps = []
    try:
        caps = ctx.client.get_capabilities(match)
    except Exception:
        pass
    note = "native tools ✓" if "tools" in caps else "no native tool support — will use JSON fallback"
    console.print(Text(f"  switched to {match} ", style="tool.ok") +
                  Text(f"({ctx.agent.context_window():,} ctx, {note})", style="muted"))


def _effort(ctx, arg):
    console = ctx.console
    if not arg:
        console.print(Text(f"  effort: {ctx.config.effort}", style="orbit"))
        console.print(Text("  levels: " + " → ".join(EFFORT_LEVELS), style="muted"))
        return
    level = arg.lower()
    if level not in EFFORT_LEVELS:
        console.print(Text(f"  unknown level {arg!r}. pick: {', '.join(EFFORT_LEVELS)}", style="tool.err"))
        return
    ctx.config.effort = level
    ctx.config.save()
    note = ""
    if level in ("xhigh", "max", "ultracode"):
        note = " (beyond 'high' this raises the output budget and pushes the prompt harder; " \
               "only gpt-oss models get a deeper native reasoning mode)"
    console.print(Text(f"  effort set to {level}", style="tool.ok") + Text(note, style="dim"))


def _plan(ctx, arg):
    from .planning import SURVEY_PROMPT
    ctx.agent.plan_mode = True
    ctx.console.print(Text("  ⊘ plan mode — read-only. It will survey the code, then propose.", style="plan"))
    if not arg:
        ctx.console.print(Text("  describe the task and it'll plan it, or /accept to leave plan mode.", style="muted"))
        return
    return CommandResult(submit=f"{SURVEY_PROMPT}\n\n---\n\nThe task:\n{arg}")


def _theme(ctx, arg):
    from .ui.picker import Option, select_one
    from .ui.theme import build_theme, theme_options

    name = arg.strip().lower()
    if not name:
        name = select_one(
            "Pick a theme",
            [Option(n, d + ("  ← current" if n == ctx.config.theme else "")) for n, d in theme_options()],
        )
        if name is None:
            return
    if name not in dict(theme_options()):
        ctx.console.print(Text(f"  unknown theme {name!r}. options: "
                               f"{', '.join(n for n, _ in theme_options())}", style="tool.err"))
        return
    ctx.config.theme = name
    ctx.config.save()
    # Rebuilding the console's theme in place keeps every existing reference valid.
    ctx.console.push_theme(build_theme(name))
    ctx.console.print(Text(f"  theme set to {name}", style="tool.ok"))
    from .ui.diff import render_diff
    from .ui.art import sample_code_block
    render_diff(ctx.console, sample_code_block(), path="src/orbit.py")


def _accept(ctx, arg):
    if not ctx.agent.plan_mode:
        ctx.console.print(Text("  not in plan mode.", style="muted"))
        return
    ctx.agent.plan_mode = False
    ctx.console.print(Text("  ▸ plan accepted — edits and commands enabled.", style="tool.ok"))
    return CommandResult(submit="Execute the plan you just described. Work through it step by step.")


def _todos(ctx, arg):
    if TODO_STORE.is_empty:
        ctx.console.print(Text("  no task list yet.", style="muted"))
        return
    render_todos(ctx.console, TODO_STORE)


def _jobs(ctx, arg):
    jobs = JOBS.all()
    if not jobs:
        ctx.console.print(Text("  no background jobs.", style="muted"))
        return
    if arg.startswith("kill"):
        target = arg.split(maxsplit=1)[1] if " " in arg else ""
        if target == "all":
            ctx.console.print(Text(f"  stopped {JOBS.kill_all()} jobs.", style="tool.ok"))
        elif JOBS.kill(target):
            ctx.console.print(Text(f"  stopped {target}.", style="tool.ok"))
        else:
            ctx.console.print(Text(f"  couldn't stop {target!r}.", style="tool.err"))
        return
    t = _table("job", "status", "elapsed", "command")
    for j in jobs:
        status = Text("running", style="tool.running") if j.running else Text(f"exit {j.returncode}", style="muted")
        t.add_row(j.id, status, f"{time.time() - j.started:.0f}s", j.command[:60])
    ctx.console.print(t)
    ctx.console.print(Text("  /jobs kill <id|all> to stop one", style="dim"))


def _permissions(ctx, arg):
    a = arg.lower()
    if a in ("on", "true", "yes"):
        ctx.config.yolo = True
    elif a in ("off", "false", "no"):
        ctx.config.yolo = False
    else:
        ctx.config.yolo = not ctx.config.yolo
    state = ("ON — tool calls auto-approved (destructive ones still ask)"
             if ctx.config.yolo else "off — you'll be asked before mutating actions")
    ctx.console.print(Text(f"  auto-accept: {state}", style="warn" if ctx.config.yolo else "muted"))


def _answer(decision):
    def handler(ctx, arg):
        runner = getattr(ctx, "runner", None)
        if runner is None or not runner.answer_approval(decision):
            ctx.console.print(Text("  nothing pending approval.", style="muted"))
    return handler


def _answer_question(ctx, arg):
    runner = getattr(ctx, "runner", None)
    pending = runner.pending_question if runner else None
    if not pending:
        ctx.console.print(Text("  nothing pending — no question was asked.", style="muted"))
        return
    options = pending["options"]

    def resolve_one(token: str):
        token = token.strip()
        if token.isdigit():
            i = int(token) - 1
            return options[i]["label"] if 0 <= i < len(options) else None
        matches = [o["label"] for o in options if o["label"].lower().startswith(token.lower())]
        return matches[0] if len(matches) == 1 else None

    if not arg:
        ctx.console.print(Text("  usage: /answer <number>" +
                               (" (comma-separate for several)" if pending["multi_select"] else ""),
                               style="tool.err"))
        return

    tokens = [t for t in arg.split(",")] if pending["multi_select"] else [arg]
    chosen = [resolve_one(t) for t in tokens]
    if any(c is None for c in chosen):
        ctx.console.print(Text(f"  couldn't match {arg!r} to an option — pick a number 1-{len(options)}.",
                               style="tool.err"))
        return

    answer = chosen if pending["multi_select"] else chosen[0]
    runner.answer_question(answer)
    shown = ", ".join(chosen)
    ctx.console.print(Text(f"  → {shown}", style="tool.ok"))


def _add(ctx, arg):
    console = ctx.console
    if not arg:
        console.print(Text("  usage: /add <path>   (or just write @path in your message)", style="tool.err"))
        return
    p = Path(arg).expanduser()
    if not p.exists():
        console.print(Text(f"  no such file: {p}", style="tool.err"))
        return
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        console.print(Text(f"  couldn't read {p}: {e}", style="tool.err"))
        return
    ctx.agent.messages.append({"role": "user", "content": f"Contents of {p}:\n\n```\n{text}\n```"})
    ctx.agent.refresh_budget()
    console.print(Text(f"  added {p} ({len(text.splitlines()):,} lines)", style="muted"))


def _diff(ctx, arg):
    from .tools import git as git_tools
    result = git_tools.diff(str(ctx.cwd), staged=(arg == "staged"))
    if not result.ok:
        ctx.console.print(Text(f"  {result.error}", style="tool.err"))
    elif "(no changes)" in result.output:
        ctx.console.print(Text("  no changes.", style="muted"))
    else:
        render_diff(ctx.console, result.output, max_lines=400)


def _undo(ctx, arg):
    entry = session_mod.pop_last_edit(ctx.cwd)
    if not entry:
        ctx.console.print(Text("  nothing to undo.", style="muted"))
        return
    p = Path(entry["path"])
    from .tools.fs import REGISTRY, _write_text  # same UTF-8 + newline-preserving write as edit_file
    try:
        if entry["existed"]:
            err = _write_text(p, entry["old_text"])
            if err:
                raise OSError(err)
            ctx.console.print(Text(f"  reverted {p}", style="tool.ok"))
        else:
            p.unlink(missing_ok=True)
            ctx.console.print(Text(f"  removed {p} (it didn't exist before)", style="tool.ok"))
        REGISTRY.forget(p)
    except OSError as e:
        ctx.console.print(Text(f"  undo failed: {e}", style="tool.err"))


def _stats(ctx, arg):
    a = ctx.agent
    elapsed = time.time() - a.started
    t = _table("metric", "value")
    t.add_row("model", a.model)
    t.add_row("session", f"{elapsed / 60:.0f} min")
    t.add_row("turns", str(a.turns))
    t.add_row("tool calls", str(a.tool_calls))
    t.add_row("tokens generated", f"{a.total_tokens:,}")
    t.add_row("files changed", str(len(a.files_changed)))
    t.add_row("approvals", f"{a.permissions.approved_count} allowed / {a.permissions.denied_count} denied")
    t.add_row("undo depth", str(session_mod.journal_depth(ctx.cwd)))
    t.add_row("cost", "$0.00 — it's your GPU")
    ctx.console.print(t)
    if a.files_changed:
        ctx.console.print(Text("  changed: " + ", ".join(sorted(a.files_changed)[:10]), style="muted"))


def _sessions(ctx, arg):
    metas = session_mod.list_sessions(ctx.cwd)
    if not metas:
        ctx.console.print(Text("  no saved sessions yet.", style="muted"))
        return
    t = _table("id", "when", "turns", "model", "first message")
    for m in metas:
        t.add_row(m.id, m.age, str(m.turns), m.model.split(":")[0][:14], m.title(50))
    ctx.console.print(t)
    ctx.console.print(Text("  /resume <id> to reload one", style="dim"))


def _resume(ctx, arg):
    payload, meta = session_mod.load_session(ctx.cwd, arg or None)
    if not payload:
        ctx.console.print(Text("  no matching session.", style="tool.err"))
        return
    messages = payload.get("messages") or []
    if not messages:
        ctx.console.print(Text("  that session has no messages.", style="tool.err"))
        return
    ctx.agent.messages = messages
    ctx.agent.turns = payload.get("turns", 0)
    ctx.agent.total_tokens = payload.get("total_tokens", 0)
    ctx.agent.tool_calls = payload.get("tool_calls", 0)
    ctx.agent.files_changed = set(payload.get("files_changed") or [])
    ctx.agent._sync_system_prompt(ctx.agent._supports_tools(ctx.agent.model))
    ctx.agent.refresh_budget()
    ctx.session.id = meta.id
    ctx.console.print(Text(f"  resumed {meta.id} — {meta.turns} turns, {len(messages)} messages", style="tool.ok"))
    ctx.console.print(Text(f"  {meta.title(70)}", style="muted"))


def _export(ctx, arg):
    dest = Path(arg).expanduser() if arg else ctx.cwd / f"geocentric-{ctx.session.id}.md"
    try:
        ctx.session.export_markdown(ctx.agent, dest)
    except OSError as e:
        ctx.console.print(Text(f"  export failed: {e}", style="tool.err"))
        return
    ctx.console.print(Text(f"  wrote {dest}", style="tool.ok"))


def _review(ctx, arg):
    from .tools import git as git_tools
    result = git_tools.diff(str(ctx.cwd))
    staged = git_tools.diff(str(ctx.cwd), staged=True)
    body = ""
    if result.ok and "(no changes)" not in result.output:
        body += result.output
    if staged.ok and "(no changes)" not in staged.output:
        body += "\n" + staged.output
    if not body.strip():
        ctx.console.print(Text("  nothing to review — working tree is clean.", style="muted"))
        return
    return CommandResult(submit=(
        "Review these uncommitted changes as a careful senior engineer would. Look for bugs, "
        "missed edge cases, and anything inconsistent with the surrounding code. Be specific and "
        "cite file:line. If it looks good, say so briefly rather than inventing problems.\n\n"
        f"```diff\n{body[:20000]}\n```"
    ))


def _test(ctx, arg):
    if arg:
        return CommandResult(submit=f"Run this test command and fix any failures: {arg}")
    hints = []
    for name, cmd in [
        ("pytest.ini", "pytest"), ("pyproject.toml", "pytest"), ("package.json", "npm test"),
        ("Cargo.toml", "cargo test"), ("go.mod", "go test ./..."), ("Makefile", "make test"),
    ]:
        if (ctx.cwd / name).exists():
            hints.append(cmd)
    guess = hints[0] if hints else None
    prompt = ("Find and run this project's test suite, then report the results. "
              "If tests fail, diagnose why and fix them.")
    if guess:
        prompt += f" It looks like `{guess}` may be the right command — verify before assuming."
    return CommandResult(submit=prompt)


def _commit(ctx, arg):
    if arg:
        return CommandResult(submit=f"Commit the current changes with this message: {arg}")
    return CommandResult(submit=(
        "Review the staged and unstaged changes with git_status and git_diff, then create a "
        "commit with a clear, specific message describing what changed and why. Follow the "
        "style of recent commits in git_log."
    ))


def _init(ctx, arg):
    return CommandResult(submit=(
        "Explore this project and write a GEOCENTRIC.md briefing at its root for future agent "
        "sessions. Use project_overview first, then read the key manifests and a few source files. "
        "Cover: what the project is, how it's laid out, how to build/run/test it, and any "
        "conventions a newcomer would otherwise get wrong. Keep it under 400 words, concrete and "
        "specific — no filler. Write the file with write_file when you're done."
    ))


_HANDLERS = {
    "/help": _help, "/banner": _banner, "/system": _system, "/clear": _clear,
    "/compact": _compact, "/context": _context, "/tools": _tools, "/models": _models,
    "/model": _model, "/effort": _effort, "/plan": _plan, "/accept": _accept,
    "/todos": _todos, "/jobs": _jobs, "/permissions": _permissions, "/yolo": _permissions,
    "/approve": _answer(Decision.ALLOW_ONCE), "/deny": _answer(Decision.DENY),
    "/always": _answer(Decision.ALLOW_ALWAYS), "/answer": _answer_question,
    "/add": _add, "/diff": _diff, "/undo": _undo,
    "/stats": _stats, "/sessions": _sessions, "/resume": _resume, "/export": _export,
    "/review": _review, "/test": _test, "/commit": _commit, "/init": _init,
    "/theme": _theme,
}
