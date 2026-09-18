"""ASCII art and decorative bits.

The orrery is the through-line: Geocentric's whole conceit is that your machine is the
center of the system and the models orbit it, so the ornament is a little solar system
rather than generic boxes.
"""
from __future__ import annotations

import random

from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.text import Text

WORDMARK = r"""    __ _  ___  ___   ___ ___ _ __ | |_ _ __(_) ___
   / _` |/ _ \/ _ \ / __/ _ \ '_ \| __| '__| |/ __|
  | (_| |  __/ (_) | (_|  __/ | | | |_| |  | | (__
   \__, |\___|\___/ \___\___|_| |_|\__|_|  |_|\___|
   |___/"""

# The orrery: your machine at the center, models in orbit around it.
ORRERY = r"""
                    ·  ˚      *          .
             .            ___
                    ·   /     \    ·           *
         *            /   ___   \        .
                 .   |   / ⌂ \   |   ·
                     |   \___/   |          ·
          ·           \    ·    /     *
                   *   \_______/   .
              .              ·            ·
                    *   ·        .    *
"""

SMALL_ORRERY = r"""       ·   ___   ·
        _/ ⌂ \_
       ·  \___/   ·"""

# Rendered under the welcome header during onboarding.
ROCKET = r"""
              /\
             /  \
            |    |
            |geo |
            |    |
           /|    |\
          / |    | \
         |  |    |  \
         |__|____|___|
            /_\/_\
           * ~ * ~ *
"""

STARS = "·˚*.✦✧⋆"


def starfield(width: int = 76, height: int = 3, density: float = 0.06) -> Text:
    """A sprinkle of stars, for spacing that isn't just blank lines."""
    t = Text()
    for _ in range(height):
        row = "".join(random.choice(STARS) if random.random() < density else " "
                      for _ in range(width))
        t.append(row + "\n", style="brand.dim")
    return t


def divider(label: str = "", width: int = 74, style: str = "rule") -> Text:
    if not label:
        return Text("─" * width, style=style)
    left = "── "
    right = " " + "─" * max(width - len(label) - len(left) - 1, 0)
    t = Text(left, style=style)
    t.append(label, style="brand")
    t.append(right, style=style)
    return t


def welcome_header(version: str) -> Panel:
    body = Group(
        Text(ORRERY.rstrip("\n"), style="brand.dim"),
        Align.center(Text("G E O C E N T R I C", style="brand")),
        Align.center(Text("your machine at the center of the system", style="brand.dim")),
        Text(""),
        Align.center(Text(f"v{version}  ·  first run", style="muted")),
    )
    return Panel(body, border_style="rule", padding=(1, 2))


def step_header(n: int, total: int, title: str) -> Text:
    t = Text(f"\n  step {n}/{total}  ", style="muted")
    t.append(title, style="brand")
    t.append("\n")
    return t


def sample_code_block() -> str:
    """Used in onboarding to preview how diffs will look."""
    return (
        "--- src/orbit.py\n"
        "+++ src/orbit.py\n"
        "@@ -1,5 +1,7 @@ compute the transfer\n"
        " def transfer(r1, r2):\n"
        "-    return 0\n"
        "+    a = (r1 + r2) / 2\n"
        "+    return 2 * math.pi * math.sqrt(a ** 3 / MU)\n"
        " \n"
        " MU = 3.986e14\n"
    )


def farewell() -> Text:
    lines = [
        "the epicycles rest.",
        "orbit complete.",
        "the spheres fall silent.",
        "back to the center.",
        "see you in the next revolution.",
    ]
    return Text(f"  {random.choice(lines)}", style="brand.dim")
