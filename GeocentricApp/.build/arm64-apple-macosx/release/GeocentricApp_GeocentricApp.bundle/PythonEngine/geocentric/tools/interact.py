"""Letting the agent ask the user things instead of guessing.

A local 9-14B model guesses badly when a request is ambiguous, and a wrong guess costs
far more than a question does - it burns a slow generation, edits the wrong file, and
then needs undoing. Giving it a real way to ask converts that whole failure mode into
a few keypresses.

This tool doesn't draw anything itself - the picker is a prompt_toolkit Application and
those can only safely run through the main thread's event loop (see runner.py's
ask_questions for the mechanics). ASK_HANDLER, set by cli.py, is the bridge.
"""
from __future__ import annotations

from .base import ToolResult

# Set by cli.py at startup. Signature: (items) -> list[answer] | None
#   items: [{"question": str, "options": [{"label","description"}], "multi_select": bool}, ...]
#   returns one answer per item (str, or list[str] for multi_select), or None if the
#   whole thing was cancelled.
ASK_HANDLER = None


def set_ask_handler(fn) -> None:
    global ASK_HANDLER
    ASK_HANDLER = fn


def _parse_options(raw: list) -> list:
    parsed = []
    for o in raw or []:
        if isinstance(o, dict):
            label = str(o.get("label") or o.get("value") or "").strip()
            desc = str(o.get("description") or "").strip()
        else:
            label, desc = str(o).strip(), ""
        if label:
            parsed.append({"label": label, "description": desc})
    return parsed


def ask_user(
    question: str = None,
    options: list = None,
    multi_select: bool = False,
    questions: list = None,
):
    """Accepts either one question (question/options/multi_select) or several at once
    via `questions` - a short wizard presented one screen at a time. Both forms are
    normalized to the same internal shape."""
    items = []

    if questions:
        for q in questions:
            if not isinstance(q, dict):
                return ToolResult(ok=False, error="each entry in 'questions' must be an object")
            items.append({
                "question": str(q.get("question") or "").strip(),
                "options": _parse_options(q.get("options")),
                "multi_select": bool(q.get("multi_select", False)),
            })
    elif question:
        items.append({
            "question": question.strip(),
            "options": _parse_options(options),
            "multi_select": bool(multi_select),
        })
    else:
        return ToolResult(ok=False, error="Provide 'question' + 'options', or a 'questions' list for several.")

    for item in items:
        if not item["question"]:
            return ToolResult(ok=False, error="Each question needs non-empty text.")
        if not item["options"]:
            return ToolResult(ok=False, error=f"{item['question']!r} needs at least one option.")

    if ASK_HANDLER is None:
        # No interactive surface (one-shot mode, piped input). Say so plainly rather
        # than hanging forever waiting for an answer that can't arrive.
        return ToolResult(
            ok=False,
            error=("No interactive surface available, so the user can't be asked right now. "
                   "Make a reasonable assumption, state it explicitly, and continue."),
        )

    answers = ASK_HANDLER(items)
    if answers is None:
        return ToolResult(
            ok=True,
            output="The user dismissed the question(s) without answering. Proceed with your "
                   "best judgement, or ask again more simply if you genuinely cannot continue.",
            meta={"cancelled": True},
        )

    lines = []
    for item, ans in zip(items, answers):
        shown = ", ".join(ans) if isinstance(ans, list) else str(ans)
        lines.append(f"- {item['question']} -> {shown}")
    return ToolResult(ok=True, output="The user answered:\n" + "\n".join(lines), meta={"answers": answers})
