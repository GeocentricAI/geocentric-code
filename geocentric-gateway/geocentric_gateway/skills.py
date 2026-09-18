"""Lists "skills" for GET /api/skills.

Geocentric's custom-command convention (.geocentric/commands/*.md, one prompt
template per file - see geocentric/commands.py's load_custom_commands) is
normally scoped to a single project checkout. The gateway has no single
project - each chat gets its own throwaway workspace - so skills live in one
shared directory instead, available to every chat: ~/.geocentric-gateway/skills/.
Drop any of geocentric's own example commands (or new ones) in there to make
them available from the web chat.
"""
from __future__ import annotations

from pathlib import Path

from .chats import HOME

SKILLS_DIR = HOME / "skills"


def _describe(path: Path) -> str:
    try:
        body = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    return body.splitlines()[0][:160] if body else ""


def list_skills() -> list:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(SKILLS_DIR.glob("*.md")):
        out.append({
            "id": p.stem,
            "name": f"/{p.stem}",
            "description": _describe(p) or "Custom command",
        })
    return out
