"""Entry point: argument parsing, the REPL, and one-shot mode."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, PathCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.text import Text

from . import __version__, commands, onboarding, planning
from . import platform_compat as pc
from . import session as session_mod
from . import tools as tools_mod
from .agent import Agent
from .config import Config, pick_random_default_model, project_dir
from .context import AUTO_CONTEXT_CAP, resolve_window
from .ollama_client import OllamaClient, OllamaConnectionError
from .permissions import Decision, PermissionManager
from .runner import Runner
from .safety import WorkspaceGuard
from .tools.interact import set_ask_handler
from .tools.settings import set_context_controller
from .ui import art
from .ui.banner import render_banner
from .ui.picker import Option, select_one
from .ui.render import render_error, render_mentions, render_permission_prompt
from .ui.theme import build_theme


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="geo",
        description="Geocentric — a local, offline coding agent powered by Ollama.",
        epilog="Run `geo` with no arguments for the interactive REPL.",
    )
    p.add_argument("prompt_args", nargs="*", help="prompt to run (same as -p, but positional)")
    p.add_argument("-p", "--print", dest="prompt", metavar="TEXT",
                   help="run one prompt non-interactively and exit")
    p.add_argument("-m", "--model", help="Ollama model to use (overrides the saved default)")
    p.add_argument("--host", help="Ollama host URL (default http://localhost:11434)")
    p.add_argument("--yolo", action="store_true", help="auto-approve tool calls (destructive ones still ask)")
    p.add_argument("--plan", action="store_true", help="start in read-only plan mode")
    p.add_argument("-C", "--cwd", default=".", help="working directory to operate in")
    p.add_argument("-c", "--continue", dest="continue_last", action="store_true",
                   help="resume the most recent session in this directory")
    p.add_argument("-r", "--resume", metavar="ID", help="resume a specific session id")
    p.add_argument("--allow-outside", action="store_true",
                   help="permit writes outside the working directory")
    p.add_argument("--no-autosave", action="store_true", help="don't persist this session to disk")
    p.add_argument("--version", action="version", version=f"geocentric {__version__}")
    return p


class GeoCompleter(Completer):
    """Live completion for /commands, their argument values, and @paths.

    Three modes, in order: the command name itself, then that command's parameters
    (model names, effort levels, session ids, job ids...), then @path anywhere in a
    normal message. Descriptions are attached as display_meta so the dropdown explains
    what each option does rather than making you guess or check /help.
    """

    def __init__(self, ctx):
        self.ctx = ctx
        self.paths = PathCompleter(expanduser=True)

    def _names(self):
        return commands.all_command_names(getattr(self.ctx, "custom_commands", {}) or {})

    def _path_completions(self, document, complete_event, fragment, meta):
        sub = Document(fragment, len(fragment))
        for c in self.paths.get_completions(sub, complete_event):
            yield Completion(c.text, start_position=c.start_position,
                             display=c.display, display_meta=meta)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        if text.startswith("/"):
            head, sep, arg = text.partition(" ")

            # Still typing the command name.
            if not sep:
                for name in self._names():
                    if name.startswith(head):
                        meta = commands.COMMAND_META.get(name, "")
                        if not meta and name in (getattr(self.ctx, "custom_commands", {}) or {}):
                            meta = "custom · " + self.ctx.custom_commands[name].splitlines()[0][:44]
                        yield Completion(name, start_position=-len(head), display=name,
                                         display_meta=meta)
                return

            # Typing the command's argument.
            cmd = head.lower()
            if cmd in commands.PATH_ARG_COMMANDS:
                yield from self._path_completions(document, complete_event, arg, "path")
                return
            for value, meta in commands.argument_options(cmd, self.ctx):
                if value.lower().startswith(arg.lower()):
                    yield Completion(value, start_position=-len(arg), display=value,
                                     display_meta=meta)
            return

        at = text.rfind("@")
        if at != -1 and (at == 0 or text[at - 1].isspace()):
            fragment = text[at + 1:]
            if " " not in fragment:
                yield from self._path_completions(document, complete_event, fragment, "attach file")


def resolve_model(client: OllamaClient, config: Config, cli_model: str, console: Console):
    """Returns (model, was_random_pick)."""
    if cli_model:
        return cli_model, False
    if config.model:
        return config.model, False
    try:
        models = client.list_models()
    except OllamaConnectionError as e:
        render_error(console, str(e))
        sys.exit(1)
    if not models:
        render_error(console, "No models in Ollama yet. Try: ollama pull qwen2.5-coder:14b")
        sys.exit(1)
    return pick_random_default_model(models), True


def make_permission_prompt(console: Console, runner_ref: dict):
    """Route approvals to whichever surface is safe for the calling thread.

    From the runner's worker thread (a turn running while the prompt is live) it has to
    go through the runner's queue-and-wait: Rich's blocking input() has no business
    running on a thread other than the one prompt_toolkit's Application owns. On the
    main thread (one-shot mode) there's no active prompt to collide with, so a direct
    blocking prompt is simpler and safe.
    """
    def prompt_fn(tool_name, args, danger, reasons=None):
        runner = runner_ref.get("runner")
        if runner is not None and threading.current_thread() is not threading.main_thread():
            return runner.request_approval(tool_name, args, danger, reasons or [])
        return render_permission_prompt(console, tool_name, args, danger, reasons or [])
    return prompt_fn


def build_key_bindings(ctx) -> KeyBindings:
    kb = KeyBindings()

    @kb.add("c-c")
    def _interrupt_or_quit(event):
        if ctx.runner.busy.is_set():
            ctx.runner.interrupt()
        else:
            event.app.exit(exception=KeyboardInterrupt)

    @kb.add("s-tab")
    def _toggle_auto_accept(event):
        ctx.config.yolo = not ctx.config.yolo
        event.app.invalidate()

    @kb.add("escape", "enter")
    def _newline(event):
        event.current_buffer.insert_text("\n")

    return kb


def make_bottom_toolbar(ctx):
    def _toolbar():
        agent = ctx.agent
        budget = agent.budget
        bits = [
            f"<b>{ctx.model.split(':')[0]}</b>",
            f"effort {ctx.config.effort}",
            f"ctx {budget.label()}",
        ]
        if agent.plan_mode:
            bits.append("PLAN (read-only)")
        bits.append("auto-accept" if ctx.config.yolo else "manual approve")

        if ctx.runner.pending_question:
            # Only the text-fallback path sets this - the picker path resolves itself
            # without any main-loop involvement, so there's nothing to show here for it.
            bits.append("❓ waiting on your answer — /answer &lt;n&gt;")
        elif ctx.runner.pending_approval:
            bits.append(f"⏸ approve {ctx.runner.pending_approval['tool']}? /approve /deny /always")
        elif agent.generating:
            label = f"running {agent.current_tool}" if agent.current_tool else agent.current_word
            bits.append(f"● {label} · {agent.live_tokens} tok (^C stops)")
        elif ctx.runner.busy.is_set():
            bits.append("● working (^C stops)")

        from .tools.todo import STORE
        summary = STORE.summary_line()
        if summary and not agent.generating:
            bits.append(f"☑ {summary}")

        return HTML(" " + "  ·  ".join(bits) + " ")
    return _toolbar


class ContextController:
    """Lets /context and the set_context_window tool change the window at runtime."""

    def __init__(self, agent, config):
        self.agent = agent
        self.config = config

    def get(self) -> int:
        return self.agent.context_window()

    def set(self, tokens: int):
        model_max = self.agent.model_max_context()
        if model_max and tokens > model_max:
            return False, (f"{self.agent.model} supports at most {model_max:,} tokens "
                           f"(you asked for {tokens:,})."), self.get()
        if tokens < 1024:
            return False, "That's too small to hold the system prompt; use at least 1024.", self.get()
        self.config.context_tokens = tokens
        self.config.save()
        self.agent.budget.window = tokens
        note = ""
        if tokens > AUTO_CONTEXT_CAP:
            note = "Larger windows reserve more GPU memory for the KV cache."
        return True, note, tokens

    def reset(self) -> int:
        self.config.context_tokens = 0
        self.config.save()
        window = resolve_window(self.agent.model_max_context(), 0)
        self.agent.budget.window = window
        return window


def make_ask_handler(ctx):
    """Route ask_user through whichever surface is safe for the calling thread.

    From the worker thread (the normal case - ask_user fires mid-turn) this goes
    through Runner.ask_questions, which renders a real arrow-key picker by scheduling
    onto the main thread's live event loop. On the main thread directly (no known call
    site today, but cheap insurance) there's no concurrent Application to collide with,
    so the picker can just run inline.
    """
    def handler(items: list):
        runner = ctx.runner
        if runner is not None and threading.current_thread() is not threading.main_thread():
            return runner.ask_questions(items)
        return _render_questions_inline(items)
    return handler


def _render_questions_inline(items: list):
    from .ui.picker import select_many, select_one
    answers = []
    for i, item in enumerate(items):
        label = item["question"]
        if len(items) > 1:
            label = f"({i + 1}/{len(items)}) {label}"
        opts = [Option(o["label"], o.get("description", "")) for o in item["options"]]
        ans = select_many(label, opts) if item["multi_select"] else select_one(label, opts)
        if ans is None:
            return None
        answers.append(ans)
    return answers


def handle_plan_decision(ctx) -> str:
    """Show the plan the agent just produced and act on the user's choice.

    Returns follow-up text to submit, or "" to stay put.
    """
    console = ctx.console
    plan = planning.parse_plan(ctx.agent.last_plan_text)
    ctx.agent.last_plan_text = ""
    planning.render_plan(console, plan)

    decision = planning.ask_decision()
    if decision == "cancel":
        console.print(Text("  plan discarded — still read-only. /accept when you're ready.", style="muted"))
        return ""
    if decision == "revise":
        console.print(Text("  what should change?", style="prompt"))
        try:
            feedback = ctx.prompt_session.prompt("  › ")
        except (EOFError, KeyboardInterrupt):
            return ""
        if not feedback.strip():
            return ""
        return planning.REVISE_PROMPT.format(feedback=feedback.strip())

    ctx.agent.plan_mode = False
    if decision == "auto":
        ctx.config.yolo = True
        console.print(Text("  ▸ executing automatically — ^C stops it.", style="tool.ok"))
    else:
        console.print(Text("  ▸ executing — you'll be asked before each change.", style="tool.ok"))
    return planning.EXECUTE_PROMPT


def _restore_session(agent, ctx, console, payload, meta) -> None:
    agent.messages = payload.get("messages") or agent.messages
    agent.turns = payload.get("turns", 0)
    agent.total_tokens = payload.get("total_tokens", 0)
    agent.tool_calls = payload.get("tool_calls", 0)
    agent.files_changed = set(payload.get("files_changed") or [])
    agent._sync_system_prompt(agent._supports_tools(agent.model))
    agent.refresh_budget()
    ctx.session.id = meta.id


def main(argv=None) -> None:
    # Both are no-ops on POSIX (already UTF-8, already ANSI-capable) and best-effort on
    # Windows: enables VT100 escape interpretation on legacy conhost.exe (Windows
    # Terminal and PowerShell 7 already have this on) - needed because the self-editing
    # status line writes raw ANSI directly, bypassing Rich's own Windows fallback
    # rendering - and reconfigures stdout/stderr to UTF-8 so redirected output
    # (`geo -p "..." > file`, piping into another tool) doesn't crash on the box-drawing
    # and emoji this UI uses once output isn't attached to a real console.
    pc.enable_windows_vt_mode()
    pc.reconfigure_stdio_utf8()

    args = build_parser().parse_args(argv)

    cwd = Path(args.cwd).expanduser().resolve()
    config_probe = Config.load(project_root=cwd)
    console = Console(theme=build_theme(config_probe.theme), highlight=False)

    if not cwd.is_dir():
        render_error(console, f"No such directory: {cwd}")
        sys.exit(1)
    os.chdir(cwd)

    config = config_probe
    if args.host:
        config.ollama_host = args.host
    if args.yolo:
        config.yolo = True
    if args.allow_outside:
        config.allow_outside_workspace = True
    if args.no_autosave:
        config.autosave_sessions = False

    client = OllamaClient(host=config.ollama_host)
    if not client.ping():
        render_error(console, f"Can't reach Ollama at {config.ollama_host}. Start it with `ollama serve`.")
        sys.exit(1)

    inline_prompt = args.prompt or (" ".join(args.prompt_args) if args.prompt_args else "")
    if onboarding.should_run(config) and not inline_prompt and sys.stdin.isatty():
        console = onboarding.run(console, config, client)

    model, was_random = resolve_model(client, config, args.model, console)
    runner_ref: dict = {}
    permissions = PermissionManager(config=config, prompt_fn=make_permission_prompt(console, runner_ref))
    guard = WorkspaceGuard(root=cwd, allow_outside=config.allow_outside_workspace)

    agent = Agent(client=client, model=model, permissions=permissions, console=console,
                  cwd=str(cwd), guard=guard)
    agent.plan_mode = args.plan

    session = session_mod.Session(cwd)
    ctx = SimpleNamespace(
        console=console, agent=agent, config=config, permissions=permissions,
        client=client, model=model, cwd=cwd, runner=None, session=session,
        custom_commands=commands.load_custom_commands(cwd),
        new_session=lambda: session_mod.Session(cwd),
    )

    set_context_controller(ContextController(agent, config))
    ctx.context_controller = ContextController(agent, config)

    # ------------------------------------------------------------------ one-shot mode
    if inline_prompt:
        set_ask_handler(None)  # nothing interactive to ask into
        agent.add_user_message(inline_prompt)
        agent.run_turn()
        if config.autosave_sessions:
            session.save(agent)
        return

    # ---------------------------------------------------------------------- interactive
    resume_id = args.resume or (None if not args.continue_last else "")
    session_note = ""
    if args.resume or args.continue_last:
        payload, meta = session_mod.load_session(cwd, resume_id or None)
        if payload:
            _restore_session(agent, ctx, console, payload, meta)
            session_note = f"resumed {meta.id} ({meta.turns} turns)"
        else:
            session_note = "no previous session found — starting fresh"

    render_banner(
        console, model=model, host=config.ollama_host, cwd=cwd, random_pick=was_random,
        context_window=agent.context_window(), tool_count=len(tools_mod.TOOLS),
        project_context=agent.project_context.describe() if not agent.project_context.is_empty else "",
        git_branch=agent._git_branch(), session_note=session_note,
    )

    # PromptSession.prompt() spins up a *fresh* event loop every call (asyncio.run()
    # internally, not a persistent one) - so "the loop" has to be recaptured at the start
    # of each call rather than once. This is what lets ask_user render a real nested
    # picker from the worker thread: it schedules onto whichever loop is live right now.
    loop_holder: dict = {"loop": None}

    def _capture_loop():
        loop_holder["loop"] = asyncio.get_running_loop()

    runner = Runner(agent, console, on_idle=lambda: config.autosave_sessions and session.save(agent),
                    loop_holder=loop_holder)
    ctx.runner = runner
    runner_ref["runner"] = runner
    set_ask_handler(make_ask_handler(ctx))

    prompt_session = PromptSession(
        history=FileHistory(str(project_dir(cwd) / "history")),
        completer=GeoCompleter(ctx),
        complete_while_typing=True,
        key_bindings=build_key_bindings(ctx),
        bottom_toolbar=make_bottom_toolbar(ctx),
    )
    ctx.prompt_session = prompt_session

    with patch_stdout(raw=True):
        while True:
            # A plan is only ever produced once run_turn has fully returned, so there's
            # no concurrent prompt() call to collide with here - safe to draw the picker
            # directly, unlike ask_user (see runner.ask_questions for why that one differs).
            if agent.last_plan_text and not runner.busy.is_set():
                follow_up = handle_plan_decision(ctx)
                if follow_up:
                    agent.add_user_message(follow_up)
                    runner.submit(follow_up, already_added=True)
                continue

            try:
                text = prompt_session.prompt("\n› ", refresh_interval=0.4, pre_run=_capture_loop)
            except (EOFError, KeyboardInterrupt):
                break

            text = text.strip()
            if not text:
                continue

            # While a question is pending, treat a bare reply ("2", "yes", the option
            # text) as an answer without making the user remember /answer exists.
            if runner.pending_question and not text.startswith("/"):
                text = "/answer " + text

            if text.startswith("/"):
                result = commands.handle(text, ctx)
                if result.quit:
                    break
                if result.submit:
                    text = result.submit
                else:
                    continue

            mentions = agent.add_user_message(text)
            if mentions:
                render_mentions(console, mentions)
            runner.submit(text, already_added=True)

    if config.autosave_sessions and agent.turns:
        session.save(agent)
        console.print(Text(f"  session saved as {session.id} — resume with `geo -c`", style="muted"))
    from .tools.shell import JOBS
    killed = JOBS.kill_all()
    if killed:
        console.print(Text(f"  stopped {killed} background job(s)", style="muted"))
    console.print(Text("goodbye.", style="brand.dim"))


if __name__ == "__main__":
    main()
