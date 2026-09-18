"""Session persistence: autosave, resume, export, and the undo journal."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import journal_path, sessions_dir


# ------------------------------------------------------------------- the undo journal

def record_edit(root: Path, path: str, old_text: str, existed: bool) -> None:
    """Append the pre-edit contents of a file so /undo can put it back."""
    entry = {"ts": time.time(), "path": path, "old_text": old_text, "existed": existed}
    try:
        with journal_path(root).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # a failed journal write must never break the edit itself


def pop_last_edit(root: Path):
    jp = journal_path(root)
    if not jp.exists():
        return None
    try:
        lines = jp.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    while lines:
        raw = lines.pop()
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        jp.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return entry
    return None


def journal_depth(root: Path) -> int:
    jp = journal_path(root)
    if not jp.exists():
        return 0
    try:
        return sum(1 for line in jp.read_text(encoding="utf-8").splitlines() if line.strip())
    except (OSError, UnicodeDecodeError):
        return 0


# ----------------------------------------------------------------------- transcripts

@dataclass
class SessionMeta:
    id: str
    path: Path
    started: float
    updated: float
    model: str = ""
    turns: int = 0
    first_prompt: str = ""
    files_changed: list = field(default_factory=list)

    @property
    def when(self) -> str:
        return datetime.fromtimestamp(self.updated).strftime("%Y-%m-%d %H:%M")

    @property
    def age(self) -> str:
        delta = time.time() - self.updated
        if delta < 3600:
            return f"{int(delta // 60)}m ago"
        if delta < 86400:
            return f"{int(delta // 3600)}h ago"
        return f"{int(delta // 86400)}d ago"

    def title(self, width: int = 60) -> str:
        text = (self.first_prompt or "(no prompt)").strip().replace("\n", " ")
        return text[:width] + ("…" if len(text) > width else "")


class Session:
    """One conversation, autosaved to .geocentric/sessions/<id>.json.

    Saving is best-effort and never raises into the agent loop - losing a transcript is
    annoying, but crashing a working session to report it would be worse.
    """

    def __init__(self, root: Path, session_id: str = None):
        self.root = root
        self.id = session_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.started = time.time()
        self.first_prompt = ""

    @property
    def path(self) -> Path:
        return sessions_dir(self.root) / f"{self.id}.json"

    def save(self, agent) -> None:
        if not self.first_prompt:
            for m in agent.messages:
                if m.get("role") == "user":
                    self.first_prompt = (m.get("content") or "")[:200]
                    break
        payload = {
            "id": self.id,
            "started": self.started,
            "updated": time.time(),
            "model": agent.model,
            "cwd": str(agent.cwd),
            "turns": agent.turns,
            "total_tokens": agent.total_tokens,
            "tool_calls": agent.tool_calls,
            "files_changed": sorted(agent.files_changed),
            "first_prompt": self.first_prompt,
            "messages": agent.messages,
        }
        try:
            self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except (OSError, TypeError):
            pass

    def export_markdown(self, agent, dest: Path) -> Path:
        lines = [
            f"# Geocentric session {self.id}",
            "",
            f"- **Model:** {agent.model}",
            f"- **Directory:** {agent.cwd}",
            f"- **Started:** {datetime.fromtimestamp(self.started).strftime('%Y-%m-%d %H:%M')}",
            f"- **Turns:** {agent.turns} · **Tool calls:** {agent.tool_calls}",
        ]
        if agent.files_changed:
            lines.append(f"- **Files changed:** {', '.join(sorted(agent.files_changed))}")
        lines.append("")

        for m in agent.messages:
            role = m.get("role")
            content = (m.get("content") or "").strip()
            if role == "system":
                continue
            if role == "user":
                lines += ["---", "", f"### 👤 User", "", content, ""]
            elif role == "assistant":
                if content:
                    lines += [f"### 🤖 Geocentric", "", content, ""]
                for call in m.get("tool_calls") or []:
                    fn = call.get("function", {})
                    lines += [f"> 🔧 `{fn.get('name')}`", ""]
            elif role == "tool":
                snippet = content[:600] + ("…" if len(content) > 600 else "")
                lines += ["```", snippet, "```", ""]

        # UTF-8 explicitly: the section headers above embed real emoji, not ASCII, and
        # write_text()'s default (the locale codepage on Windows) can't represent them.
        dest.write_text("\n".join(lines), encoding="utf-8")
        return dest


def list_sessions(root: Path, limit: int = 20) -> list:
    d = sessions_dir(root)
    metas = []
    for p in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        metas.append(
            SessionMeta(
                id=data.get("id", p.stem),
                path=p,
                started=data.get("started", p.stat().st_mtime),
                updated=data.get("updated", p.stat().st_mtime),
                model=data.get("model", ""),
                turns=data.get("turns", 0),
                first_prompt=data.get("first_prompt", ""),
                files_changed=data.get("files_changed", []),
            )
        )
    return metas


def load_session(root: Path, session_id: str = None):
    """Load a session by id, or the most recent one. Returns (payload, meta) or (None, None)."""
    metas = list_sessions(root, limit=200)
    if not metas:
        return None, None
    if session_id:
        meta = next((m for m in metas if m.id == session_id or m.id.startswith(session_id)), None)
    else:
        meta = metas[0]
    if meta is None:
        return None, None
    try:
        return json.loads(meta.path.read_text(encoding="utf-8")), meta
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None, None


def new_session_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")
