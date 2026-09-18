"""Chat metadata store + per-chat workspace directories.

Mirrors geocentric/config.py's convention of a dotfile under the home
directory for anything that isn't tied to a specific project checkout - a
gateway chat isn't scoped to "the project geo-gateway happens to be run
from", it's scoped to the user's machine.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

HOME = Path.home() / ".geocentric-gateway"
WORKSPACES_DIR = HOME / "workspaces"
STORE_PATH = HOME / "gateway.json"

_lock = threading.Lock()


def _ensure_dirs() -> None:
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)


def _load() -> dict:
    _ensure_dirs()
    if not STORE_PATH.exists():
        return {"chats": {}, "cron_jobs": {}}
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {"chats": {}, "cron_jobs": {}}
    data.setdefault("chats", {})
    data.setdefault("cron_jobs", {})
    return data


def _save(data: dict) -> None:
    _ensure_dirs()
    tmp = STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(STORE_PATH)


def workspace_dir(chat_id: str) -> Path:
    p = WORKSPACES_DIR / chat_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_chats() -> list:
    with _lock:
        data = _load()
    return sorted(data["chats"].values(), key=lambda c: c.get("updated", 0), reverse=True)


def get_chat(chat_id: str) -> Optional[dict]:
    with _lock:
        data = _load()
    return data["chats"].get(chat_id)


def upsert_chat(chat: dict) -> dict:
    """Create or update a chat record. `chat` must have an 'id'. Stores
    whatever the caller passes (the frontend posts its full client-side chat
    object - title, messages, model, timestamps - so GET /api/chats can
    round-trip it back losslessly), defaulting only bookkeeping fields."""
    chat_id = chat.get("id") or uuid.uuid4().hex[:12]
    with _lock:
        data = _load()
        existing = data["chats"].get(chat_id, {})
        record = {
            **existing,
            **chat,
            "id": chat_id,
            "title": chat.get("title") or existing.get("title") or "New chat",
            "created": existing.get("created") or time.time(),
            "updated": time.time(),
        }
        data["chats"][chat_id] = record
        _save(data)
    workspace_dir(chat_id)  # make sure it exists as soon as the chat does
    return record


def delete_chat(chat_id: str) -> bool:
    with _lock:
        data = _load()
        existed = data["chats"].pop(chat_id, None) is not None
        _save(data)
    return existed


# --------------------------------------------------------------------- cron jobs

def list_cron_jobs() -> list:
    with _lock:
        data = _load()
    return sorted(data["cron_jobs"].values(), key=lambda j: j.get("name", ""))


def get_cron_job(job_id: str) -> Optional[dict]:
    with _lock:
        data = _load()
    return data["cron_jobs"].get(job_id)


def upsert_cron_job(record: dict) -> dict:
    with _lock:
        data = _load()
        data["cron_jobs"][record["id"]] = record
        _save(data)
    return record


def touch_cron_job(job_id: str, last_run: float) -> None:
    with _lock:
        data = _load()
        if job_id in data["cron_jobs"]:
            data["cron_jobs"][job_id]["last_run"] = last_run
            _save(data)


def delete_cron_job(job_id: str) -> bool:
    with _lock:
        data = _load()
        existed = data["cron_jobs"].pop(job_id, None) is not None
        _save(data)
    return existed
