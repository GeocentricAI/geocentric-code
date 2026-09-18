"""Rendering: streamed status, tool calls, diffs, todos, prompts, stats."""
from __future__ import annotations

import random
import threading
import time

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from ..permissions import Decision
from .diff import diff_stats, render_diff
from .funny_words import random_funny_word
from .theme import DANGER_ICON, DANGER_STYLE, RANDOM_STATUS_COLORS

_CURSOR_UP_AND_CLEAR = "\x1b[1A\x1b[2K"

# Values long enough to be unreadable inline get summarized instead of dumped.
_INLINE_ARG_LIMIT = 56


def format_args(args: dict) -> str:
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        if isinstance(v, str):
            s = v.replace("\n", "⏎")
            if len(s) > _INLINE_ARG_LIMIT:
                s = f"{s[:_INLINE_ARG_LIMIT - 3]}…"
                parts.append(f"{k}={s!r} ({len(v):,} chars)")
            else:
                parts.append(f"{k}={s!r}")
        elif isinstance(v, list):
            parts.append(f"{k}=[{len(v)} items]")
        elif isinstance(v, dict):
            parts.append(f"{k}={{{len(v)} keys}}")
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts)


class AssistantStream:
    """A single self-editing status line: "● {word} • Tokens: N (X tok/s)".

    It edits one line via manual cursor-up-and-clear writes rather than Rich's Live,
    whose background auto-refresh thread fought with prompt_toolkit's redraw of the
    active input line (flicker, or a stuck line). Every reprint here is one deliberate,
    throttled write, and a lock keeps our two sources of reprints (token arrival and the
    watcher) from interleaving.

    The watcher exists because a lot of a turn's silence is prompt evaluation, before a
    single byte streams back - a purely reactive update would look identical to a hang.
    """

    MIN_INTERVAL = 0.8
    WATCHER_INTERVAL = 4.0

    def __init__(self, console: Console):
        self.console = console
        self._buf: list = []
        self._tokens = 0
        self._t0 = 0.0
        self._word = random_funny_word()
        self._color = random.choice(RANDOM_STATUS_COLORS)
        self._stop_event = threading.Event()
        self._watcher = None
        self._lock = threading.Lock()
        self._printed_once = False
        self._last_update_t = 0.0

    def start(self) -> "AssistantStream":
        self._t0 = time.time()
        self._word = random_funny_word()
        self._color = random.choice(RANDOM_STATUS_COLORS)
        self._stop_event.clear()
        self._printed_once = False
        self.console.print()
        self._reprint(done=False)
        self._watcher = threading.Thread(target=self._watch, daemon=True)
        self._watcher.start()
        return self

    def _watch(self) -> None:
        # Ticks on a wall clock so a silent stretch (prompt eval, a slow first token)
        # still shows life. Runs for the whole turn, not just until text starts.
        while not self._stop_event.wait(self.WATCHER_INTERVAL):
            self._reprint(done=False)

    def feed(self, delta: str) -> None:
        if not delta:
            return
        self._buf.append(delta)
        self._tokens += 1
        self._maybe_reprint()

    def feed_thinking(self, delta: str) -> None:
        """Reasoning tokens arrive on a separate channel and aren't shown as text, but
        they're real work - counting them is what keeps the number moving during a long
        silent reasoning stretch."""
        if not delta:
            return
        self._tokens += 1
        self._maybe_reprint()

    def _maybe_reprint(self) -> None:
        # Deliberately keeps updating after text starts arriving. An earlier version
        # stopped here on the theory that streamed text would take over the display -
        # but the answer is only printed once the turn ends, so the counter just froze
        # at whatever it read when the first token landed while the model kept working.
        if time.time() - self._last_update_t >= self.MIN_INTERVAL:
            self._reprint(done=False)

    @property
    def content(self) -> str:
        return "".join(self._buf)

    @property
    def tokens(self) -> int:
        return self._tokens

    @property
    def word(self) -> str:
        return self._word

    @property
    def tokens_per_second(self) -> float:
        return self._tokens / max(time.time() - self._t0, 0.001)

    def _status_line(self, done: bool) -> Text:
        icon = "✓" if done else "●"
        verb = f"done {self._word}" if done else self._word
        line = Text(f"{icon} {verb} ", style=self._color)
        line += Text("• ", style="dim")
        line += Text(f"Tokens: {self._tokens} ({self.tokens_per_second:.1f} tok/s)", style="dim")
        return line

    def _reprint(self, done: bool) -> None:
        with self._lock:
            if self._printed_once:
                self.console.file.write(_CURSOR_UP_AND_CLEAR)
            self.console.print(self._status_line(done))
            self._printed_once = True
            self._last_update_t = time.time()

    def stop(self) -> None:
        self._stop_event.set()
        if self._watcher:
            self._watcher.join(timeout=1)
            self._watcher = None
        with self._lock:
            if self.content.strip():
                # A real answer follows, so clear the progress line and let it take the
                # space rather than leaving a stale counter above every reply.
                if self._printed_once:
                    self.console.file.write(_CURSOR_UP_AND_CLEAR)
                    self._printed_once = False
                return
        # Nothing visible came out of this step (a tool call, or a JSON attempt about to
        # be parsed) - settle on a "done" marker so the transcript shows it happened.
        self._reprint(done=True)


def render_final_answer(console: Console, text: str) -> None:
    if not text.strip():
        return
    console.print(Padding(Markdown(text.strip()), (0, 0, 1, 0)))


class ToolCallView:
    """Header + result line for one tool call.

    `quiet` skips the spinner: during a threaded turn a live-redrawing spinner competes
    with the active prompt line, so we print the header when the call starts and the
    result when it lands instead.
    """

    def __init__(self, console: Console, name: str, args: dict, danger: str = "low", quiet: bool = False):
        self.console = console
        self.name = name
        self.args = args
        self.danger = danger
        self.quiet = quiet
        self._status = None
        self._t0 = 0.0

    def _header(self) -> Text:
        return Text("● ", style="tool") + Text(f"{self.name}", style="tool") + Text(
            f"({format_args(self.args)})", style="tool.arg"
        )

    def start(self) -> "ToolCallView":
        self._t0 = time.time()
        self.console.print(self._header())
        if not self.quiet:
            self._status = self.console.status(
                Text("  running…", style="tool.running"), spinner="dots", spinner_style="tool.running"
            )
            self._status.__enter__()
        return self

    def finish(self, result) -> None:
        if self._status:
            self._status.__exit__(None, None, None)
            self._status = None
        elapsed = time.time() - self._t0

        icon = "✓" if result.ok else "✗"
        style = "tool.ok" if result.ok else "tool.err"

        if result.diff:
            added, removed = diff_stats(result.diff)
            headline = f"{result.output or 'done'}  (+{added} -{removed})"
        elif result.ok:
            first = (result.output or "").strip().splitlines()
            headline = first[0] if first else "done"
            if len(first) > 1:
                headline += f"  (+{len(first) - 1} more lines)"
        else:
            err = (result.error or "failed").strip().splitlines()
            headline = err[0] if err else "failed"

        if len(headline) > 150:
            headline = headline[:147] + "…"

        timing = f" ({elapsed:.1f}s)" if elapsed >= 0.1 else ""
        self.console.print(Text(f"  ⎿ {icon} {headline}", style=style) + Text(timing, style="dim"))

        if result.diff:
            render_diff(self.console, result.diff, path=result.meta.get("path", ""))
        elif not result.ok and result.error:
            for line in result.error.strip().splitlines()[1:6]:
                self.console.print(Text(f"    {line[:160]}", style="dim"))


def render_todos(console: Console, store) -> None:
    if store.is_empty:
        return
    rows = []
    for t in store.items:
        if t.status == "completed":
            rows.append(Text("  ✓ ", style="todo.done") + Text(t.content, style="todo.done"))
        elif t.status == "in_progress":
            rows.append(Text("  ▸ ", style="todo.active") + Text(t.content, style="todo.active"))
        else:
            rows.append(Text("  ○ ", style="todo.pending") + Text(t.content, style="todo.pending"))
    done, total = store.counts()
    console.print()
    console.print(
        Panel(
            Group(*rows),
            title=f"[brand]tasks[/brand] [dim]{done}/{total}[/dim]",
            title_align="left",
            border_style="rule",
            padding=(0, 1),
        )
    )


def render_permission_prompt(console: Console, tool_name: str, args: dict, danger: str, reasons=None) -> Decision:
    icon = DANGER_ICON.get(danger, "○")
    style = DANGER_STYLE.get(danger, "warn")
    console.print()
    console.print(
        Text(f"  {icon} approve ", style=style)
        + Text(tool_name, style="tool")
        + Text(f"({format_args(args)})", style="tool.arg")
    )
    for reason in reasons or []:
        console.print(Text(f"    ! {reason}", style=style))

    if danger == "critical":
        console.print(Text("    this one is destructive and is asked even in auto-accept mode", style="critical"))

    choice = Prompt.ask(
        "  [prompt]allow?[/prompt] [dim]([/dim][tool.ok]y[/tool.ok][dim]es /[/dim] "
        "[tool.err]n[/tool.err][dim]o /[/dim] [orbit]a[/orbit][dim]lways this session)[/dim]",
        choices=["y", "n", "a"],
        default="y" if danger != "critical" else "n",
        console=console,
    )
    return {"y": Decision.ALLOW_ONCE, "a": Decision.ALLOW_ALWAYS, "n": Decision.DENY}[choice]


def render_approval_needed(console: Console, tool_name: str, args: dict, danger: str, reasons=None) -> None:
    icon = DANGER_ICON.get(danger, "○")
    style = DANGER_STYLE.get(danger, "warn")
    console.print()
    console.print(
        Text(f"  {icon} approval needed: ", style=style)
        + Text(tool_name, style="tool")
        + Text(f"({format_args(args)})", style="tool.arg")
    )
    for reason in reasons or []:
        console.print(Text(f"    ! {reason}", style=style))
    console.print(
        Text("    reply ", style="muted")
        + Text("/approve", style="tool.ok")
        + Text(", ", style="muted")
        + Text("/deny", style="tool.err")
        + Text(", or ", style="muted")
        + Text("/always", style="orbit")
    )


def render_question_needed(console: Console, question: str, options: list, multi: bool) -> None:
    console.print()
    console.print(Text("  ❓ ", style="orbit") + Text(question, style="assistant"))
    for i, opt in enumerate(options, 1):
        label = opt.get("label", "") if isinstance(opt, dict) else str(opt)
        desc = opt.get("description", "") if isinstance(opt, dict) else ""
        line = Text(f"    {i}. ", style="orbit") + Text(label, style="tool.arg")
        console.print(line)
        if desc:
            console.print(Text(f"       {desc}", style="dim"))
    how = "/answer 1,3 to pick several" if multi else "/answer 2  (or the number alone)"
    console.print(Text(f"    reply with {how}", style="muted"))


def render_hallucinated_tool_warning(console: Console) -> None:
    console.print(
        Text(
            "  ⚠ this model isn't tool-capable and appears to be simulating a tool call/result "
            "on its own — treat any file contents, command output, or facts below as unverified.",
            style="warn",
        )
    )


def render_plan_blocked(console: Console, tool_name: str) -> None:
    console.print(Text(f"  ⊘ {tool_name} blocked — plan mode is read-only (/accept to execute)", style="plan"))


def render_auto_compacted(console: Console, before: int, after: int) -> None:
    console.print(Text(f"  ⟳ context was {before}% full — compacted to {after}%", style="muted"))


def render_warning(console: Console, message: str) -> None:
    console.print(Text(f"  ⚠ {message}", style="warn"))


def render_error(console: Console, message: str) -> None:
    console.print(Text(f"\n✗ {message}", style="tool.err"))


def render_info(console: Console, message: str) -> None:
    console.print(Text(message, style="muted"))


def render_interrupted(console: Console) -> None:
    console.print(Text("\n⏹ interrupted.", style="warn"))


def render_queued(console: Console, text: str) -> None:
    preview = text if len(text) <= 60 else text[:57] + "…"
    console.print(Text(f"  ⧗ queued — runs when the current turn finishes: {preview!r}", style="muted"))


def render_mentions(console: Console, mentions: list) -> None:
    for m in mentions:
        if m.ok:
            kind = "dir" if m.path.is_dir() else f"{len(m.body):,} chars"
            console.print(Text(f"  @ {m.raw} ({kind})", style="muted"))
        else:
            console.print(Text(f"  @ {m.raw} — {m.error}", style="tool.err"))


def context_meter(budget) -> Text:
    style = "meter.ok" if budget.percent < 60 else ("meter.warn" if budget.percent < 85 else "meter.full")
    # Token counts rather than a bare percentage: on a big window the percentage rounds
    # to 0 and reads as "broken" when it actually means "plenty of room".
    return Text(f"{budget.bar()} {budget.label()}", style=style)


def render_stats(console: Console, result, budget=None) -> None:
    bits = []
    if result and result.tokens_per_second:
        bits.append(f"{result.eval_count} tokens · {result.tokens_per_second:.1f} tok/s")
    line = Text("  " + " · ".join(bits), style="dim") if bits else Text("  ", style="dim")
    if budget is not None:
        line += Text(" · context ", style="dim") + context_meter(budget)
    if line.plain.strip():
        console.print(line)
