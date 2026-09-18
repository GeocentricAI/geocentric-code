"""Tools that adjust geocentric's own runtime settings."""
from __future__ import annotations

from .base import ToolResult

# Set by cli.py: an object exposing get()/set()/reset() for the context window.
CONTEXT_CONTROLLER = None


def set_context_controller(controller) -> None:
    global CONTEXT_CONTROLLER
    CONTEXT_CONTROLLER = controller


def set_context_window(tokens: int = 0, reset: bool = False):
    """Change how much context is requested from Ollama.

    Worth exposing to the agent (not just the user) because the agent is the first to
    notice it's running out of room - it can raise the window mid-task instead of
    quietly losing the start of the conversation to compaction.
    """
    if CONTEXT_CONTROLLER is None:
        return ToolResult(ok=False, error="Context window control isn't available in this mode.")

    if reset:
        new = CONTEXT_CONTROLLER.reset()
        return ToolResult(
            ok=True,
            output=f"Context window reset to automatic ({new:,} tokens).",
            meta={"window": new},
        )

    try:
        tokens = int(tokens)
    except (TypeError, ValueError):
        return ToolResult(ok=False, error="'tokens' must be an integer number of tokens.")

    if tokens <= 0:
        return ToolResult(ok=False, error="'tokens' must be positive, or pass reset=true.")

    ok, message, applied = CONTEXT_CONTROLLER.set(tokens)
    if not ok:
        return ToolResult(ok=False, error=message)
    return ToolResult(
        ok=True,
        output=f"Context window set to {applied:,} tokens. {message}".strip(),
        meta={"window": applied},
    )
