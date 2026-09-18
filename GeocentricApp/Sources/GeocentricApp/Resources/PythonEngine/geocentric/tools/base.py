"""Shared tool types.

Lives in its own module so individual tool implementations can import ToolResult
directly instead of doing a lazy import inside every function to dodge a circular
import with the registry in __init__.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class ToolResult:
    ok: bool
    output: str = ""
    error: str = ""
    diff: Optional[str] = None  # unified diff, for pretty rendering on file edits
    meta: dict = field(default_factory=dict)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    required: list
    fn: Callable[..., ToolResult]
    mutating: bool  # True => needs permission unless auto-accepted
    danger: str = "low"  # low | medium | high, used for permission prompt styling
    concurrent_safe: bool = False  # read-only and side-effect free => may run in parallel
    group: str = "general"  # for /tools grouping

    def as_ollama_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": self.required,
                },
            },
        }


def truncate_output(text: str, limit: int = 12_000, keep_tail: int = 2_000) -> str:
    """Trim long tool output from the middle rather than the end.

    The tail of a build log or stack trace is usually where the answer is, so a plain
    head-truncation throws away the most useful part. Keep both ends.
    """
    if len(text) <= limit:
        return text
    head = text[: limit - keep_tail]
    tail = text[-keep_tail:]
    omitted = len(text) - len(head) - len(tail)
    return f"{head}\n\n... [{omitted:,} characters omitted] ...\n\n{tail}"
