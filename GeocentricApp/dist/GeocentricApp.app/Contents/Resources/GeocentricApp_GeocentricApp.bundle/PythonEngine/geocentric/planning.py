"""Deep plan mode: survey, propose, then execute only once you've agreed.

The value here is specific to local models. A 12B model that starts editing immediately
tends to discover halfway through that it misunderstood the layout, and by then it has
already changed four files. Forcing a read-only survey first costs one extra generation
and converts "undo this mess" into "no, do it this other way" - which is much cheaper
for both of us.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from .ui.picker import Option, select_one

SURVEY_PROMPT = """Before doing anything, survey the codebase and produce a plan.

Work read-only for now — every editing tool is blocked, so don't attempt one.

1. Orient yourself. Use project_overview, then list_dir / grep / read_file to actually
   look at the files this task touches. Do not plan against files you haven't opened.
2. Then write the plan, in this exact shape:

## Goal
One sentence on what will be true when this is done.

## Files
Each file you'll change and what changes in it. Real paths you have read.

## Steps
Numbered, ordered, concrete. Each step should be one clear action.

## Risks
Anything that could break, anything you're unsure about, anything you couldn't verify.
Say "none" only if you genuinely mean it.

## Verification
The exact command(s) you'll run to prove it worked.

Be specific and short. No filler, no restating the request. If the task is genuinely
ambiguous, use ask_user rather than guessing — that is what it is for."""

EXECUTE_PROMPT = """The user approved your plan. Execute it now.

Work through the steps in order. Track them with todo_write, marking each completed as
you actually finish it. Run the verification command at the end and report the real
result — if it fails, fix it rather than reporting success.

If reality turns out to differ from the plan, say so and adapt rather than forcing the
plan through."""

REVISE_PROMPT = """The user wants changes to the plan before you execute it.

Their feedback:
{feedback}

Revise the plan and present it again in the same format. You are still read-only, so
don't start editing. Investigate further if their feedback implies you missed something."""


@dataclass
class Plan:
    """A parsed plan. Falls back to raw text if the model didn't follow the headings."""

    raw: str
    goal: str = ""
    files: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    risks: str = ""
    verification: str = ""

    @property
    def is_structured(self) -> bool:
        return bool(self.goal or self.steps or self.files)


_HEADING_RE = re.compile(r"^\s{0,3}#{1,4}\s*(goal|files|steps|risks|verification)\b.*$",
                         re.IGNORECASE | re.MULTILINE)


def parse_plan(text: str) -> Plan:
    plan = Plan(raw=text or "")
    if not text:
        return plan

    sections, last_key, last_pos = {}, None, 0
    for m in _HEADING_RE.finditer(text):
        if last_key:
            sections[last_key] = text[last_pos:m.start()].strip()
        last_key = m.group(1).lower()
        last_pos = m.end()
    if last_key:
        sections[last_key] = text[last_pos:].strip()

    plan.goal = sections.get("goal", "").strip()
    plan.risks = sections.get("risks", "").strip()
    plan.verification = sections.get("verification", "").strip()

    def bullets(body: str) -> list:
        out = []
        for line in (body or "").splitlines():
            line = line.strip()
            if not line:
                continue
            cleaned = re.sub(r"^([-*+]|\d+[.)])\s*", "", line).strip()
            if cleaned:
                out.append(cleaned)
        return out

    plan.files = bullets(sections.get("files", ""))
    plan.steps = bullets(sections.get("steps", ""))
    return plan


def render_plan(console, plan: Plan) -> None:
    if not plan.is_structured:
        # Model ignored the format - show what it did say rather than pretending to parse.
        console.print(Panel(Markdown(plan.raw or "_(empty plan)_"),
                            title="[plan]proposed plan[/plan]", title_align="left",
                            border_style="plan", padding=(1, 2)))
        return

    blocks = []
    if plan.goal:
        blocks.append(Text(plan.goal, style="assistant"))

    if plan.files:
        blocks.append(Text("\nfiles", style="brand"))
        for f in plan.files:
            blocks.append(Text("  · ", style="dim") + Text(f, style="tool.arg"))

    if plan.steps:
        blocks.append(Text("\nsteps", style="brand"))
        for i, s in enumerate(plan.steps, 1):
            blocks.append(Text(f"  {i}. ", style="orbit") + Text(s, style="assistant"))

    if plan.risks and plan.risks.lower().strip(" .") not in ("none", "n/a"):
        blocks.append(Text("\nrisks", style="warn"))
        for r in plan.risks.splitlines():
            r = re.sub(r"^([-*+]|\d+[.)])\s*", "", r.strip())
            if r:
                blocks.append(Text("  ! ", style="warn") + Text(r, style="muted"))

    if plan.verification:
        blocks.append(Text("\nverify with", style="brand"))
        for v in plan.verification.splitlines():
            v = re.sub(r"^([-*+]|\d+[.)])\s*", "", v.strip())
            if v:
                blocks.append(Text("  $ ", style="tool.ok") + Text(v, style="tool.arg"))

    console.print()
    console.print(Panel(Group(*blocks), title="[plan]proposed plan[/plan]", title_align="left",
                        border_style="plan", padding=(1, 2)))


DECISION_OPTIONS = [
    Option("Accept — run it, ask before each change", "you approve each edit and command", value="manual"),
    Option("Accept — run it automatically", "no prompts except genuinely destructive commands", value="auto"),
    Option("Request changes", "tell it what to reconsider; it replans", value="revise"),
    Option("Cancel", "discard the plan and stay read-only", value="cancel"),
]


def ask_decision() -> str:
    """Returns 'manual' | 'auto' | 'revise' | 'cancel'."""
    return select_one("How do you want to proceed?", DECISION_OPTIONS, allow_cancel=True) or "cancel"
