"""Color themes. Cosmic palette by default: the universe orbits your code."""
from __future__ import annotations

from rich.theme import Theme

# Structural styles are identical across themes; only the accent colors change. Keeping
# one shape means a new theme is a handful of colors, not a full restatement.
_SHARED = {
    "assistant": "bright_white",
    "assistant.dim": "grey62",
    "tool.ok": "bold spring_green2",
    "tool.err": "bold red3",
    "tool.running": "bold yellow3",
    "tool.skip": "grey50",
    "diff.add": "spring_green3",
    "diff.add.mark": "bold spring_green2",
    "diff.remove": "red3",
    "diff.remove.mark": "bold red3",
    "diff.context": "grey62",
    "diff.hunk": "italic grey54",
    "diff.gutter": "grey37",
    "diff.gutter.add": "spring_green4",
    "diff.gutter.remove": "dark_red",
    "diff.meta": "grey42",
    "todo.done": "spring_green4",
    "todo.active": "bold gold1",
    "todo.pending": "grey62",
    "warn": "bold gold3",
    "danger": "bold red1",
    "critical": "bold white on red3",
    "dim": "dim",
    "muted": "grey62",
    "rule": "grey35",
    "meter.ok": "spring_green3",
    "meter.warn": "gold3",
    "meter.full": "red3",
}

THEMES = {
    "geocentric": {
        "_desc": "cosmic purple — the default",
        "brand": "bold medium_orchid1", "brand.dim": "medium_orchid3",
        "orbit": "bold cyan", "sun": "bold gold1", "user": "bold deep_sky_blue1",
        "tool": "bold cyan", "tool.arg": "cyan", "prompt": "bold medium_orchid1",
        "plan": "bold cyan",
    },
    "solar": {
        "_desc": "warm gold and amber",
        "brand": "bold gold1", "brand.dim": "dark_goldenrod",
        "orbit": "bold orange1", "sun": "bold yellow1", "user": "bold orange3",
        "tool": "bold orange1", "tool.arg": "light_goldenrod3", "prompt": "bold gold1",
        "plan": "bold orange1",
    },
    "nebula": {
        "_desc": "pink and magenta",
        "brand": "bold hot_pink", "brand.dim": "orchid",
        "orbit": "bold plum2", "sun": "bold magenta", "user": "bold pink1",
        "tool": "bold plum2", "tool.arg": "plum4", "prompt": "bold hot_pink",
        "plan": "bold plum2",
    },
    "voyager": {
        "_desc": "cool blues and teal",
        "brand": "bold deep_sky_blue1", "brand.dim": "steel_blue",
        "orbit": "bold turquoise2", "sun": "bold cyan1", "user": "bold sky_blue2",
        "tool": "bold turquoise2", "tool.arg": "cadet_blue", "prompt": "bold deep_sky_blue1",
        "plan": "bold turquoise2",
    },
    "eclipse": {
        "_desc": "high-contrast monochrome",
        "brand": "bold white", "brand.dim": "grey58",
        "orbit": "bold bright_white", "sun": "bold white", "user": "bold grey85",
        "tool": "bold grey85", "tool.arg": "grey62", "prompt": "bold white",
        "plan": "bold grey85",
    },
}


def build_theme(name: str = "geocentric") -> Theme:
    palette = THEMES.get(name) or THEMES["geocentric"]
    styles = dict(_SHARED)
    styles.update({k: v for k, v in palette.items() if not k.startswith("_")})
    return Theme(styles)


def theme_options() -> list:
    return [(name, cfg["_desc"]) for name, cfg in THEMES.items()]


GEOCENTRIC_THEME = build_theme("geocentric")

DANGER_STYLE = {
    "low": "tool.ok",
    "medium": "warn",
    "high": "danger",
    "critical": "critical",
}

DANGER_ICON = {
    "low": "○",
    "medium": "◐",
    "high": "●",
    "critical": "⚠",
}

# A fresh one is picked each time the thinking indicator starts, so the color changes
# step to step along with the funny word.
RANDOM_STATUS_COLORS = [
    "medium_orchid1", "deep_sky_blue1", "spring_green2", "gold1", "hot_pink",
    "cyan", "turquoise2", "orange3", "chartreuse2", "sky_blue2", "plum2",
    "khaki1", "salmon1", "light_slate_blue", "aquamarine1", "pale_green1",
    "light_coral", "sandy_brown", "violet", "dodger_blue1", "yellow2",
    "spring_green1", "orchid", "steel_blue1", "light_pink1", "gold3",
    "cadet_blue", "medium_purple2", "tan", "light_sea_green",
]
