"""Inline arrow-key selectors.

Deliberately *not* prompt_toolkit's `radiolist_dialog` and friends: those take over the
whole screen, wipe the transcript, and pop it back afterwards, which is jarring in the
middle of a conversation. These render in place, scroll away with everything else, and
leave a record of what was asked and answered.

Must run on the main thread - a prompt_toolkit Application owns the terminal while it
runs. Anything on the worker thread routes through Runner.ask_question instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style

PICKER_STYLE = Style.from_dict({
    "q": "bold #d787ff",
    "sel": "bold #5fd7ff",
    "opt": "#c6c6c6",
    "desc": "#767676",
    "mark": "bold #5fff87",
    "hint": "#767676 italic",
    "num": "#585858",
})


@dataclass
class Option:
    label: str
    description: str = ""
    value: object = None

    def resolved(self):
        return self.value if self.value is not None else self.label


def _normalize(options) -> List[Option]:
    out = []
    for o in options:
        if isinstance(o, Option):
            out.append(o)
        elif isinstance(o, (tuple, list)):
            out.append(Option(label=str(o[0]), description=str(o[1]) if len(o) > 1 else ""))
        elif isinstance(o, dict):
            out.append(Option(label=str(o.get("label", o.get("value", "?"))),
                              description=str(o.get("description", "")),
                              value=o.get("value")))
        else:
            out.append(Option(label=str(o)))
    return out


def _build_app(question: str, options: List[Option], multi: bool, allow_cancel: bool):
    """Builds (but does not run) the picker Application, plus its mutable state dict.

    Split from running it so callers can choose `app.run()` (blocking, for the main
    thread with no other Application active) or `await app.run_async()` (for running
    nested inside another Application's event loop - see runner.py's cross-thread
    ask_user path for why that distinction matters).
    """
    state = {"cursor": 0, "checked": set(), "result": None, "cancelled": False}

    def render():
        lines = [("class:q", f"\n  {question}\n")]
        for i, opt in enumerate(options):
            active = i == state["cursor"]
            arrow = "❯ " if active else "  "
            if multi:
                box = "[✔]" if i in state["checked"] else "[ ]"
            else:
                box = "◉" if active else "○"
            style = "class:sel" if active else "class:opt"
            lines.append((f"class:num", f"  {arrow}"))
            lines.append(("class:mark" if (multi and i in state["checked"]) else style, f"{box} "))
            lines.append((style, f"{opt.label}\n"))
            if opt.description:
                lines.append(("class:desc", f"       {opt.description}\n"))
        hint = "space toggles · enter confirms" if multi else "↑↓ to move · enter to select"
        if allow_cancel:
            hint += " · esc cancels"
        lines.append(("class:hint", f"\n  {hint}\n"))
        return FormattedText(lines)

    kb = KeyBindings()

    @kb.add("up")
    @kb.add("c-p")
    @kb.add("k")
    def _up(event):
        state["cursor"] = (state["cursor"] - 1) % len(options)

    @kb.add("down")
    @kb.add("c-n")
    @kb.add("j")
    def _down(event):
        state["cursor"] = (state["cursor"] + 1) % len(options)

    @kb.add("tab")
    def _tab(event):
        state["cursor"] = (state["cursor"] + 1) % len(options)

    @kb.add("space")
    def _space(event):
        if multi:
            state["checked"].symmetric_difference_update({state["cursor"]})

    for n in range(1, min(len(options), 9) + 1):
        @kb.add(str(n))
        def _num(event, n=n):
            state["cursor"] = n - 1
            if not multi:
                state["result"] = [n - 1]
                event.app.exit()

    @kb.add("enter")
    def _enter(event):
        if multi:
            state["result"] = sorted(state["checked"]) or [state["cursor"]]
        else:
            state["result"] = [state["cursor"]]
        event.app.exit()

    @kb.add("escape", eager=True)
    @kb.add("c-c")
    def _cancel(event):
        if allow_cancel:
            state["cancelled"] = True
            event.app.exit()

    app = Application(
        layout=Layout(HSplit([Window(FormattedTextControl(render), dont_extend_height=True)])),
        key_bindings=kb,
        style=PICKER_STYLE,
        full_screen=False,
        erase_when_done=False,
    )
    return app, state


def _resolve(state, options: List[Option], multi: bool):
    if state["cancelled"] or state["result"] is None:
        return None
    if multi:
        return [options[i].resolved() for i in state["result"]]
    return options[state["result"][0]].resolved()


def select_one(question: str, options, allow_cancel: bool = True) -> Optional[object]:
    """Single-choice picker. Blocking - only call this where no other prompt_toolkit
    Application is concurrently active on another thread. Returns the chosen option's
    value, or None if cancelled."""
    opts = _normalize(options)
    if not opts:
        return None
    app, state = _build_app(question, opts, multi=False, allow_cancel=allow_cancel)
    app.run()
    return _resolve(state, opts, multi=False)


def select_many(question: str, options, allow_cancel: bool = True) -> Optional[list]:
    """Multi-choice picker. Same threading rule as select_one."""
    opts = _normalize(options)
    if not opts:
        return None
    app, state = _build_app(question, opts, multi=True, allow_cancel=allow_cancel)
    app.run()
    return _resolve(state, opts, multi=True)


async def select_one_async(question: str, options, allow_cancel: bool = True) -> Optional[object]:
    """Async form of select_one, for running nested inside another Application's loop
    (see ask_question_in_terminal). Never call this from a different thread than the
    one actually running that loop."""
    opts = _normalize(options)
    if not opts:
        return None
    app, state = _build_app(question, opts, multi=False, allow_cancel=allow_cancel)
    await app.run_async()
    return _resolve(state, opts, multi=False)


async def select_many_async(question: str, options, allow_cancel: bool = True) -> Optional[list]:
    opts = _normalize(options)
    if not opts:
        return None
    app, state = _build_app(question, opts, multi=True, allow_cancel=allow_cancel)
    await app.run_async()
    return _resolve(state, opts, multi=True)


def confirm(question: str, default_yes: bool = True) -> bool:
    choice = select_one(
        question,
        [Option("Yes", value=True), Option("No", value=False)] if default_yes
        else [Option("No", value=False), Option("Yes", value=True)],
        allow_cancel=False,
    )
    return bool(choice)
