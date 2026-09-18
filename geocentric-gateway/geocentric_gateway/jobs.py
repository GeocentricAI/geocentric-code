"""In-memory registry of agent jobs, polled by the frontend via
GET /api/chat/jobs/{id}.

Lives entirely on the asyncio event loop thread (server.py runs a single
uvicorn worker), so plain dicts are safe without locking as long as nothing
here ever awaits mid-mutation - it doesn't. cron.py, which runs its own
scheduling thread, always hops back onto the loop via
run_coroutine_threadsafe before touching this module.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from . import chats

# status: "running" | "completed" | "failed" - these three exact strings are
# load-bearing: web/index.html's pollAgentJob/finishJobInUi branch on them
# literally ("queued"/"running" = still polling, "completed" = render
# job.reply, "failed" = render job.error). Anything else is silently ignored
# by the frontend and the UI just hangs on "Working on your request...".
#
# ask_user questions don't get a special status: gui_bridge's question_request
# event is formatted as a Q:/A: block (see tags.py's companion in bridge.py)
# and the job simply completes with that block as its reply. The frontend
# already renders Q:/A: blocks as clickable choice cards (parseQABlocks /
# injectQAChoices) and resubmits the chosen title as an ordinary chat message
# - bridge.py notices the session still has a pending question and forwards
# that next message as an answer instead of a new prompt.


@dataclass
class Job:
    id: str
    chat_id: str
    user_text: str = ""
    status: str = "running"
    progress: str = ""
    reply: str = ""
    error: str = ""
    roadmap: str = ""
    persisted: bool = False  # has this turn's (user_text, reply) been written to chats.py yet?
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)


_JOBS: dict = {}
# last known roadmap per chat, so GET /api/workspaces/{chatId}/roadmap works
# even after the job that produced it is gone.
_ROADMAPS: dict = {}


def create(chat_id: str, user_text: str = "") -> Job:
    job = Job(id=uuid.uuid4().hex[:12], chat_id=chat_id, user_text=user_text)
    _JOBS[job.id] = job
    return job


def get(job_id: str) -> Optional[Job]:
    return _JOBS.get(job_id)


def append_progress(job_id: str, text: str) -> None:
    job = _JOBS.get(job_id)
    if job is None or not text:
        return
    job.progress += text
    job.updated = time.time()


def set_roadmap(job_id: str, text: str) -> None:
    job = _JOBS.get(job_id)
    if job is None:
        return
    job.roadmap = text
    _ROADMAPS[job.chat_id] = text
    job.updated = time.time()


def roadmap_for_chat(chat_id: str) -> str:
    return _ROADMAPS.get(chat_id, "")


def complete(job_id: str, reply: str) -> None:
    job = _JOBS.get(job_id)
    if job is None:
        return
    job.status = "completed"
    job.reply = reply
    job.updated = time.time()


def fail(job_id: str, message: str) -> None:
    job = _JOBS.get(job_id)
    if job is None:
        return
    job.status = "failed"
    job.error = message
    job.updated = time.time()


def all_jobs() -> list:
    """For GET /api/chat/jobs (bare) - resumeAgentJobs() calls this once on
    page load to reattach polling to anything still running after a refresh."""
    return list(_JOBS.values())


def latest_job_for_chat(chat_id: str) -> Optional[Job]:
    candidates = [j for j in _JOBS.values() if j.chat_id == chat_id]
    return max(candidates, key=lambda j: j.created) if candidates else None


def _last_matches(messages: list, role: str, content: str) -> bool:
    return bool(messages) and messages[-1].get("role") == role and messages[-1].get("content") == content


def persist_turn(job: Job) -> None:
    """Writes a finished turn into the chat's server-side record (chats.py)
    so it shows up in GET /api/chats even for chats no browser ever polled -
    a cron-triggered job's target chat has no browser watching it at all, so
    if nothing here wrote the result down it would run for real (the file
    gets written, the command gets run) and then vanish with no transcript.

    For interactive chats the browser already saves its own copy of the user
    turn via saveChatToServer() moments before this usually runs (from the
    GET /api/chat/jobs/{id} poll), so each append is skipped if the record
    already ends with that exact message - otherwise the two writes race and
    the frontend renders the user's bubble twice after a refresh."""
    if job.persisted or job.status == "running":
        return
    job.persisted = True
    reply_text = job.reply or (f"Error: {job.error}" if job.error else "")
    record = chats.get_chat(job.chat_id) or {"id": job.chat_id}
    messages = list(record.get("messages") or [])
    before = len(messages)
    if job.user_text and not _last_matches(messages, "user", job.user_text):
        messages.append({"role": "user", "content": job.user_text})
    if reply_text and not _last_matches(messages, "assistant", reply_text):
        messages.append({"role": "assistant", "content": reply_text})
    if len(messages) > before:
        chats.upsert_chat({**record, "messages": messages})


def as_created_dict(job: Job) -> dict:
    """Shape for POST /api/chat/jobs - the frontend reads jobData.jobId here
    (see the sendMessage() call site in web/index.html), not jobData.id."""
    return {
        "jobId": job.id,
        "chatId": job.chat_id,
        "status": job.status,
        "progress": job.progress,
        "roadmap": job.roadmap,
    }


def as_poll_dict(job: Job) -> dict:
    """Shape for GET /api/chat/jobs/{id} - pollAgentJob/finishJobInUi read
    job.id (not job.jobId) here, and expect the whole thing wrapped as
    {"job": ...} by the caller (see get_job in server.py)."""
    return {
        "id": job.id,
        "chatId": job.chat_id,
        "status": job.status,
        "progress": job.progress,
        "reply": job.reply,
        "error": job.error,
        "roadmap": job.roadmap,
    }
