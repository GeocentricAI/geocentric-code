"""The opening banner. Geocentric: the universe orbits your code."""
from __future__ import annotations

import random

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from .. import __version__

TAGLINES = [
    "the universe, orbiting your codebase",
    "every model is just a moon in your orbit",
    "zero tokens billed, infinite epicycles",
    "your GPU is now the center of the universe",
    "Ptolemy would have loved local inference",
    "no cloud required — the sky's the limit, literally",
    "all your epicycles are belong to you",
    "spherical code, in a vacuum",
    "the stars are just other people's data centers",
]

LOGO = r"""    __ _  ___  ___   ___ ___ _ __ | |_ _ __(_) ___
   / _` |/ _ \/ _ \ / __/ _ \ '_ \| __| '__| |/ __|
  | (_| |  __/ (_) | (_|  __/ | | | |_| |  | | (__
   \__, |\___|\___/ \___\___|_| |_|\__|_|  |_|\___|
   |___/"""


def render_banner(console, *, model, host, cwd, version_note="", random_pick=False,
                  context_window=0, project_context="", tool_count=0, git_branch="",
                  session_note="") -> None:
    rows = [Text(LOGO, style="brand"), Text("")]
    rows.append(Text(f"  {random.choice(TAGLINES)}", style="brand.dim"))
    rows.append(Text(""))

    def row(label, value, style="assistant"):
        line = Text(f"  {label:<9}", style="muted")
        line.append(value, style=style)
        return line

    model_note = model
    if random_pick:
        model_note += "  🎲 rolled from your 9–14B lineup"
    if context_window:
        model_note += f"  ·  {context_window // 1024}k ctx"
    rows.append(row("model", model_note, "orbit"))

    where = str(cwd)
    if git_branch:
        where += f"  ({git_branch})"
    rows.append(row("cwd", where))
    rows.append(row("ollama", host, "muted"))
    if project_context:
        rows.append(row("context", project_context, "tool.ok"))
    if session_note:
        rows.append(row("session", session_note, "muted"))
    rows.append(row("ready", f"{tool_count} tools · geocentric v{__version__}", "muted"))

    rows.append(Text(""))
    hint = Text("  ")
    for label, desc in [("/help", "commands"), ("@file", "add context"), ("/plan", "think first"),
                        ("shift+tab", "auto-accept"), ("^C", "interrupt")]:
        hint.append(label, style="prompt")
        hint.append(f" {desc}   ", style="muted")
    rows.append(hint)

    console.print(Panel(Group(*rows), border_style="rule", padding=(0, 1)))
