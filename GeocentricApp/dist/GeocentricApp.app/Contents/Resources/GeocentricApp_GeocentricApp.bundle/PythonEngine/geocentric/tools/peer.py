"""Delegating a sub-task to a paired Mac, once orchestration mode is active.

Only useful in orchestration mode: cluster mode instead hands whole inference calls to
an `exo` cluster (see cluster_mode.py), so there's no "other agent" to talk to there.
DELEGATE_HANDLER is set by gui_bridge.py, same wiring pattern as tools/interact.py's
ASK_HANDLER - this module stays free of any direct dependency on ClusterNode.
"""
from __future__ import annotations

from .base import ToolResult

# Set by gui_bridge.py. Signature: (task: str) -> str
DELEGATE_HANDLER = None


def set_delegate_handler(fn) -> None:
    global DELEGATE_HANDLER
    DELEGATE_HANDLER = fn


def delegate_to_peer(task: str):
    """Hand a self-contained sub-task to the paired Mac's own agent, running on its own
    model in parallel with this one. Read-only for now (the peer investigates/analyzes/
    drafts; it doesn't write files) - fold its answer into your own work rather than
    trusting it blindly."""
    if not task or not task.strip():
        return ToolResult(ok=False, error="Provide a self-contained task description - the peer has no memory of this conversation.")
    if DELEGATE_HANDLER is None:
        return ToolResult(ok=False, error="Not linked with another Mac in orchestration mode.")
    result = DELEGATE_HANDLER(task.strip())
    if result.startswith("ERROR:"):
        return ToolResult(ok=False, error=result)
    return ToolResult(ok=True, output=result)
