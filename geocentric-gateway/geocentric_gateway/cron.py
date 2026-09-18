"""Scheduled jobs.

The frontend already renders a specific shape for these - {name,
interval_hours, interval_minutes, model, prompt, last_run} (see
loadCronJobs() in web/index.html) - a plain repeat-every-N interval, not real
cron syntax. A background thread checks every 30s whether any job is due and,
if so, hops onto the main asyncio loop to dispatch that job's prompt into its
own dedicated chat via the same bridge.py path an interactive message uses.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from typing import Optional

from . import bridge, chats, jobs

CHECK_INTERVAL_SECONDS = 30

_loop: Optional[asyncio.AbstractEventLoop] = None
_thread: Optional[threading.Thread] = None
_stop = threading.Event()


def list_jobs() -> list:
    return chats.list_cron_jobs()


def create_job(body: dict) -> dict:
    job_id = uuid.uuid4().hex[:12]
    chat_id = uuid.uuid4().hex[:12]
    name = (body.get("name") or "Scheduled task").strip()
    record = {
        "id": job_id,
        "name": name,
        "interval_hours": max(0, int(body.get("interval_hours") or 0)),
        "interval_minutes": max(0, int(body.get("interval_minutes") or 0)),
        "model": (body.get("model") or "").strip(),
        "prompt": (body.get("prompt") or "").strip(),
        "chat_id": chat_id,
        "last_run": time.time(),  # counts from creation, not "overdue immediately"
    }
    chats.upsert_cron_job(record)
    chats.upsert_chat({"id": chat_id, "title": name, "model": record["model"]})
    return record


def delete_job(job_id: str) -> bool:
    return chats.delete_cron_job(job_id)


def _due(record: dict, now: float) -> bool:
    interval_seconds = record.get("interval_hours", 0) * 3600 + record.get("interval_minutes", 0) * 60
    if interval_seconds <= 0:
        return False
    return now - record.get("last_run", 0) >= interval_seconds


async def _fire(record: dict) -> None:
    # No browser is watching a cron-triggered chat, so nothing else will ever
    # poll GET /api/chat/jobs/{id} for it - without waiting here and
    # persisting the result ourselves, the job would run for real (files
    # written, commands run) and then its transcript would just vanish.
    try:
        session = await bridge.MANAGER.get_or_create(record["chat_id"], model=record.get("model") or None)
        job = await session.dispatch(record["prompt"])
        while job.status == "running":
            await asyncio.sleep(1.0)
        jobs.persist_turn(job)
    except Exception:
        pass  # a failed scheduled run must not take the scheduler thread down with it


def _tick() -> None:
    now = time.time()
    for record in list_jobs():
        if not _due(record, now):
            continue
        chats.touch_cron_job(record["id"], now)
        if _loop is not None:
            asyncio.run_coroutine_threadsafe(_fire(record), _loop)


def _run_loop() -> None:
    while not _stop.is_set():
        _tick()
        _stop.wait(CHECK_INTERVAL_SECONDS)


def start(loop: asyncio.AbstractEventLoop) -> None:
    global _loop, _thread
    _loop = loop
    _stop.clear()
    _thread = threading.Thread(target=_run_loop, daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
