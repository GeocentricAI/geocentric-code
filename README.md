# Geocentric

A local coding agent for your terminal. Same shape as Claude Code or Codex CLI — plan,
read, edit, run, verify — except the model lives on your machine via
[Ollama](https://ollama.com) and nothing ever leaves it. No API keys, no per-token bill,
no network dependency once the model is pulled.

```
› guard div() against division by zero in @app/calc.py

● todo_write(todos=[3 items])
  ⎿ ✓ Updated task list (0/3 complete)

╭─ tasks 0/3 ──────────────────────────────────────────╮
│   ▸ Read calc.py and the project layout              │
│   ○ Add a zero-division guard to div()               │
│   ○ Verify with a quick run                          │
╰──────────────────────────────────────────────────────╯

● read_file(path='app/calc.py')
● project_overview(path='.')
● grep(pattern='def ', path='.')          ← these three ran in parallel
  ⎿ ✓ 1 def add(a, b):  (+5 more lines)
  ⎿ ✓ Project: calc  (+8 more lines)
  ⎿ ✓ 2 matches

● multi_edit(path='app/calc.py', edits=[1 items])
  ⎿ ✓ applied 1 edits  (+2 -0)
     ⋮
    5 def div(a, b):
    6 +    if b == 0:
    7 +        raise ValueError("cannot divide by zero")
    8     return a / b

Added a zero-division guard to app/calc.py:5 and verified add() still works.
  48 tokens · 96.0 tok/s · context ██░░░░░░░░ 20%
```

## Install

Needs Python 3.9+ and a running Ollama daemon with at least one model pulled.

**macOS / Linux:**

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -e .
```

To use `geo` from anywhere without activating the venv:

```bash
mkdir -p ~/.local/bin && ln -sf "$PWD/.venv/bin/geo" ~/.local/bin/geo
```

(then make sure `~/.local/bin` is on your `PATH`)

**Windows:** install [Ollama for Windows](https://ollama.com/download/windows) and pull a
model first (`ollama pull qwen2.5-coder:14b`), then:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

(If PowerShell blocks the activation script: `Set-ExecutionPolicy -Scope Process
RemoteSigned` first, or use `.venv\Scripts\activate.bat` from `cmd.exe` instead.)

`geo` is now on `PATH` for that venv - `.venv\Scripts\geo.exe`. To use it from anywhere
without activating: add `<project>\.venv\Scripts` to your `PATH` (System Properties →
Environment Variables), or `pipx install -e .` instead of the venv above, which does
that for you. Symlinks aren't the right tool here - Windows requires either an elevated
shell or Developer Mode to create one without admin rights, so there's no reason to
reach for `ln -s`.

Geocentric runs shell commands through PowerShell on Windows (not `cmd.exe`) for its
much better overlap with the Unix commands a model reaches for by habit - see
[Safety](#safety) for what the risk classifier covers there.

## Use

```bash
geo                              # interactive REPL in the current directory
geo "add a healthcheck endpoint" # one-shot: run a prompt and exit
geo -c                           # resume the most recent session here
geo --plan                       # start in read-only planning mode
geo -m qwen3-coder:30b           # pin a model for this run
geo --yolo                       # auto-approve (destructive commands still ask)
```

With no model pinned, Geocentric rolls the dice each launch among your local models in
the 9–14B range, preferring coding-tuned ones. Pin a favourite with `/model <name>`.

## What it can do

**22 tools.** Read, write, `edit_file` (exact-string), `multi_edit` (atomic multi-hunk),
list, `grep` (ripgrep-backed), glob, `project_overview`, shell, Python, background jobs
(`check_job`/`kill_job`/`list_jobs`), a full git set, `todo_write` for the task list,
`ask_user` to ask you a question, and `set_context_window` to grow its own context
mid-task.

**Parallel reads.** When the model asks for several independent read-only tools at once,
they run concurrently. Writes and shell commands stay strictly sequential — interleaving
those would be a correctness bug, not a speedup.

**Plan mode.** `/plan <task>` puts the agent in read-only mode and makes it survey the
codebase first — every mutating tool is blocked and it only sees the read-only tool
schema. It comes back with a structured plan (goal, files, steps, risks, verification),
rendered as a panel, and you pick:

```
  ❯ ◉ Accept — run it, ask before each change
    ○ Accept — run it automatically
    ○ Request changes
    ○ Cancel
```

"Request changes" sends your feedback back and it replans. This matters more locally
than it does with a hosted model: a 12B model that starts editing immediately tends to
discover halfway through that it misread the layout, by which point it's changed four
files. One extra read-only pass turns "undo this mess" into "no, do it this way".

**It can ask you things.** When a request is genuinely ambiguous, the agent uses
`ask_user` to put up an arrow-key picker rather than guessing — a wrong guess costs a
slow generation plus an undo, a question costs one keypress.

**Onboarding and themes.** First run walks through theme, model, effort and approval
mode in four steps, previewing a real diff so you can see what you're picking. Five
themes (`geocentric`, `solar`, `nebula`, `voyager`, `eclipse`), switchable any time with
`/theme`.

**Context management.** Auto-loads `GEOCENTRIC.md`, `AGENTS.md`, `CLAUDE.md`, or
`.cursorrules` (walking up for monorepos). `@path` in a message attaches that file, with
tab-completion. The status bar shows real usage (`1.2k/16k`), and it auto-compacts at 75%
instead of silently overflowing.

One thing worth knowing, because it bites every Ollama client: **Ollama ignores a model's
advertised context length by default.** `gpt-oss:20b` reports 131,072 tokens, but unless
the Modelfile sets `num_ctx` (most don't) Ollama quietly uses its own 4096 default and
truncates the front of your conversation. Geocentric always sends `num_ctx` explicitly —
auto-capped at 16k, since KV-cache memory scales linearly with it and this is your GPU.
Change it with `/context set 32768` or `/context reset`; `/context` shows the real number
against what the model could do.

**Sessions.** Every session autosaves. `/sessions` lists them, `/resume` reloads one,
`/export` writes the transcript to markdown, `/undo` reverts the last edit.

**Custom commands.** Drop a markdown file in `.geocentric/commands/` and it becomes a
slash command; `$ARGUMENTS` is replaced with whatever follows it. Two examples ship in
this repo — `/explain` and `/harden`.

### Slash commands

| | |
|---|---|
| `/help` `/clear` `/compact` `/context` `/theme` | session basics |
| `/sessions` `/resume [id]` `/export` `/stats` | history |
| `/model` `/models` `/effort` | which brain, how hard it thinks |
| `/plan` `/accept` `/todos` | plan-then-execute workflow |
| `/diff` `/undo` `/review` `/test` `/commit` | code workflow |
| `/tools` `/jobs` `/permissions` | control |
| `/approve` `/deny` `/always` | answer a pending approval |

### While it's working

The prompt never blocks. Keep typing (messages queue), run read-only commands mid-turn,
**Ctrl+C** to interrupt just that turn, **Shift+Tab** to toggle auto-accept on the fly.

## Safety

Read-only tools run freely. Mutating ones ask first, and the prompt tells you *why* it's
risky — `git push --force` reads as "force-push rewrites remote history", not just
"run_command".

- Writes are confined to your working directory. Anything outside needs explicit
  approval every time (`--allow-outside` to relax).
- `~/.ssh`, `~/.aws`, `~/.gnupg`, `/etc`, `.git` internals and friends are never
  writable, full stop.
- Files that look like credentials (`.env`, `*.pem`, `id_rsa`) always prompt.
- Genuinely destructive commands (`rm -rf /`, fork bombs, `curl | sh`, disk writes) are
  confirmed **even with auto-accept on**. Auto-accept exists to skip fifty `read_file`
  prompts, not to hand over an unattended disk wipe.
- Edits to files that changed on disk since the agent read them are refused, so it can't
  clobber an edit you made in your editor.

This is guardrails, not a sandbox: a local agent running local shell commands has your
privileges by definition. The goal is making the *accidental* catastrophe hard and the
deliberate one visible.

**On Windows**, the protected-path and destructive-command lists are platform-aware, not
just carried over from macOS/Linux unchanged: writes to `C:\Windows`, `%ProgramFiles%`,
`%ProgramData%`, and `%AppData%` are blocked the same way `/etc` and `/usr` are on POSIX,
and the risk classifier recognizes PowerShell/cmd equivalents of the dangerous stuff
(`Remove-Item -Recurse -Force` against a drive root, `iwr … | iex`, `vssadmin delete
shadows`, `Set-ExecutionPolicy Bypass`, and so on) rather than only knowing `rm -rf` and
`curl | sh`.

## A note on local models and tool calling

Local models vary wildly here, and it's the single biggest determinant of whether this
feels great or frustrating. `/models` shows which of yours actually support tool calling
and thinking:

```
  model                       size      params    tools    think
  cogito:14b ●                8.4GB     ~14B      ✓        —
  deepseek-coder-v2:latest    8.3GB     ~13.8B    —        —
  gpt-oss:20b                 12.8GB    ~20B      ✓        ✓
```

Geocentric handles the awkward cases rather than just failing:

- **No native tool support** → tools are described in the system prompt and it parses the
  JSON convention back out.
- **Model uses its own pretrained dialect** (DeepSeek's `<｜tool▁call▁begin｜>`,
  Hermes-style `<tool_call>`) → detected mid-stream and the model is stopped the instant
  the call completes, *before* it can hallucinate a fake result, then the real tool runs.
- **Model fakes a tool result anyway** in a dialect we don't recognize → flagged loudly
  so you don't trust invented output.

Still, a tool-capable model is dramatically better. `qwen3-coder`, `cogito`, `gemma4`,
and `gpt-oss` all call tools cleanly.

`/effort` (`low` → `ultracode`) controls the thinking budget. Ollama exposes no generic
reasoning-token knob, so this adjusts whether `think` is requested, the output budget,
and how hard the prompt pushes for deliberation. Only `gpt-oss` models get a truly
graduated native reasoning mode.

## Layout

```
geocentric/
  cli.py          entry point, REPL, key bindings, completion
  agent.py        the tool-calling loop, dialect detection, parallel dispatch
  runner.py       background turn execution, interrupts, approval queue
  prompts.py      system prompts
  context.py      project briefings, @mentions, token budget, stale-file registry
  safety.py       workspace guard, dangerous-command classification
  platform_compat.py  Windows/POSIX differences: shell, jobs, paths, encoding, console
  permissions.py  approval flow
  session.py      autosave, resume, export, undo journal
  config.py       global + per-project config, effort profiles
  tools/          base, fs, search, shell, git, todo
  ui/             theme, render, diff, banner, funny_words
```
