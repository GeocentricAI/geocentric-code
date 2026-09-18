"""First-run setup.

Deliberately short - four questions and a preview. An onboarding flow that takes longer
than the thing it's introducing is a tax, not a welcome. Everything here is changeable
later with a slash command, and that's said out loud at the end so nothing feels locked in.
"""
from __future__ import annotations

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from . import __version__
from .config import EFFORT_LEVELS, Config, _guess_param_size_b
from .ui import art
from .ui.diff import render_diff
from .ui.picker import Option, select_one
from .ui.theme import build_theme, theme_options

TOTAL_STEPS = 4


def should_run(config: Config) -> bool:
    return not config.onboarded


def run(console: Console, config: Config, client) -> Console:
    """Walk through setup. Returns a console using the chosen theme."""
    console.print()
    console.print(art.welcome_header(__version__))
    console.print(Text(
        "  Geocentric is a coding agent that runs entirely on your machine.\n"
        "  No API keys, no per-token bill, nothing leaves this computer.\n",
        style="muted",
    ))

    # ---------------------------------------------------------------- 1. theme
    console.print(art.step_header(1, TOTAL_STEPS, "Pick a look"))
    theme_name = select_one(
        "Which color theme suits your terminal?",
        [Option(name, desc) for name, desc in theme_options()],
        allow_cancel=False,
    ) or "geocentric"
    config.theme = theme_name
    console = Console(theme=build_theme(theme_name), highlight=False)
    console.print(Text(f"  ✓ {theme_name}", style="tool.ok"))

    # Show the theme doing real work, since a swatch tells you nothing useful.
    console.print(Text("\n  Diffs will look like this:", style="muted"))
    render_diff(console, art.sample_code_block(), path="src/orbit.py")

    # ---------------------------------------------------------------- 2. model
    console.print(art.step_header(2, TOTAL_STEPS, "Choose a model"))
    model = _pick_model(console, client)
    if model:
        config.model = model
        console.print(Text(f"  ✓ {model}", style="tool.ok"))
    else:
        console.print(Text("  ✓ a 9–14B model will be picked at random each launch", style="tool.ok"))

    # ---------------------------------------------------------------- 3. effort
    console.print(art.step_header(3, TOTAL_STEPS, "How hard should it think?"))
    effort = select_one(
        "Thinking effort — you can change this any time with /effort.",
        [
            Option("low", "fastest replies, no deliberation"),
            Option("medium", "balanced — a good default"),
            Option("high", "thinks before answering, noticeably slower"),
        ],
        allow_cancel=False,
    ) or "medium"
    config.effort = effort
    console.print(Text(f"  ✓ {effort}", style="tool.ok"))

    # ---------------------------------------------------------------- 4. approvals
    console.print(art.step_header(4, TOTAL_STEPS, "How much rope?"))
    mode = select_one(
        "When the agent wants to edit a file or run a command:",
        [
            Option("Ask me first", "you approve each change — recommended to start", value="ask"),
            Option("Auto-accept", "runs without asking; genuinely destructive commands still stop", value="auto"),
        ],
        allow_cancel=False,
    ) or "ask"
    config.yolo = (mode == "auto")
    console.print(Text(f"  ✓ {'auto-accept' if config.yolo else 'ask first'}", style="tool.ok"))

    config.onboarded = True
    config.save()

    tips = Group(
        Text("You're set. A few things worth knowing:\n", style="assistant"),
        _tip("@path", "attach a file to your message (tab-completes)"),
        _tip("/plan", "make it investigate and propose before touching anything"),
        _tip("/help", "every command, grouped"),
        _tip("shift+tab", "flip auto-accept mid-session"),
        _tip("ctrl+c", "interrupt the current turn without quitting"),
        Text("\nSettings live in ~/.geocentric/config.json — /theme, /model and /effort change them.",
             style="dim"),
    )
    console.print()
    console.print(Panel(tips, border_style="rule", padding=(1, 2),
                        title="[brand]ready[/brand]", title_align="left"))
    return console


def _tip(key: str, text: str) -> Text:
    t = Text("  ")
    t.append(f"{key:<12}", style="prompt")
    t.append(text, style="muted")
    return t


def _pick_model(console: Console, client):
    """Offer the local models, tool-capable ones first - that's what actually matters."""
    try:
        models = client.list_models()
    except Exception:
        console.print(Text("  (couldn't reach Ollama to list models — will decide later)", style="warn"))
        return None
    if not models:
        console.print(Text("  No models pulled yet. Try: ollama pull qwen2.5-coder:14b", style="warn"))
        return None

    scored = []
    for m in models:
        name = m.get("name") or m.get("model")
        size_b = _guess_param_size_b(name, m.get("size", 0))
        try:
            caps = client.get_capabilities(name)
        except Exception:
            caps = []
        has_tools = "tools" in caps
        is_coder = any(k in name.lower() for k in ("coder", "code", "dev"))
        # Tool support dominates: without it every edit goes through a fallback parser.
        rank = (has_tools, is_coder, 9.0 <= size_b <= 14.0, -abs(size_b - 12))
        bits = []
        bits.append("tools ✓" if has_tools else "no tool support")
        if "thinking" in caps:
            bits.append("thinking")
        bits.append(f"{m.get('size', 0) / (1024 ** 3):.1f}GB")
        scored.append((rank, Option(name, " · ".join(bits))))

    scored.sort(key=lambda x: x[0], reverse=True)
    options = [opt for _, opt in scored[:8]]
    options.append(Option("Surprise me each launch", "random 9–14B model, coder-tuned if available",
                          value="__random__"))

    choice = select_one("Which model should be the default?", options, allow_cancel=False)
    return None if choice in (None, "__random__") else choice
