"""A live task checklist the agent maintains as it works.

Two things make this worth a tool rather than just prose. First, it forces the model to
commit to a plan before it starts editing, which measurably reduces the "confidently did
the wrong three things" failure mode that smaller local models are prone to. Second, it
gives the user a real progress display on long tasks instead of a spinner and hope.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .base import ToolResult

VALID_STATUSES = ("pending", "in_progress", "completed")


@dataclass
class Todo:
    content: str
    status: str = "pending"


@dataclass
class TodoStore:
    items: list = field(default_factory=list)
    version: int = 0  # bumped on each change so the UI knows to re-render

    def replace(self, raw_items: list) -> tuple:
        """Returns (ok, error). Validates before mutating so a bad call is a no-op."""
        parsed = []
        for entry in raw_items:
            if not isinstance(entry, dict):
                return False, "each todo must be an object with 'content' and 'status'"
            content = (entry.get("content") or entry.get("task") or "").strip()
            status = (entry.get("status") or "pending").strip().lower()
            if not content:
                return False, "every todo needs a non-empty 'content'"
            if status not in VALID_STATUSES:
                return False, f"invalid status {status!r}; use one of {', '.join(VALID_STATUSES)}"
            parsed.append(Todo(content=content, status=status))

        active = [t for t in parsed if t.status == "in_progress"]
        if len(active) > 1:
            return False, "only one todo may be 'in_progress' at a time"

        self.items = parsed
        self.version += 1
        return True, ""

    def clear(self) -> None:
        self.items = []
        self.version += 1

    @property
    def is_empty(self) -> bool:
        return not self.items

    def counts(self) -> tuple:
        done = sum(1 for t in self.items if t.status == "completed")
        return done, len(self.items)

    def summary_line(self) -> str:
        done, total = self.counts()
        if not total:
            return ""
        current = next((t.content for t in self.items if t.status == "in_progress"), None)
        head = f"{done}/{total} done"
        return f"{head} · {current}" if current else head

    def as_text(self) -> str:
        """Plain-text form fed back to the model so it can see its own list."""
        if not self.items:
            return "(no todos)"
        marks = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}
        return "\n".join(f"{marks[t.status]} {t.content}" for t in self.items)


# One store per process. The agent, the tool function, and the UI all need to see the
# same list, and threading it through every call site would be noise for no benefit.
STORE = TodoStore()


def todo_write(todos: list):
    if not isinstance(todos, list):
        return ToolResult(ok=False, error="'todos' must be a list of {content, status} objects")
    ok, err = STORE.replace(todos)
    if not ok:
        return ToolResult(ok=False, error=err)
    done, total = STORE.counts()
    return ToolResult(
        ok=True,
        output=f"Updated task list ({done}/{total} complete):\n{STORE.as_text()}",
        meta={"todo_update": True, "version": STORE.version},
    )
