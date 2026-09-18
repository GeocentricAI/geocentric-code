"""Owns one geocentric.gui_bridge subprocess per chat and translates its
structured JSON event stream into the tag vocabulary web/index.html already
parses (see tags.py). One subprocess per chat sidesteps geocentric's
process-global tool state (TodoStore, the shell-jobs registry) rather than
fighting it - each chat gets a fully isolated Agent/Runner/session.

Sessions are started with --yolo (permission bubbles have no matching UI in
this frontend); geocentric's safety.py still hard-blocks genuinely destructive
commands regardless of yolo, so this narrows what needs approval rather than
removing the guardrail entirely.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

from . import chats, jobs, tags

_BRIDGE_MODULE = "geocentric.gui_bridge"

# Deliberately NOT geocentric.config.Config.load()'s ollama_host: that reads
# ~/.geocentric/config.json, which is shared with the plain `geo` CLI and may
# well point at a *remote* Ollama (cloud-hosted, or someone else's machine on
# the LAN) with an API key on file - entirely legitimate for that CLI, but a
# silent violation of this app's one promise ("local ai agents... nothing
# ever leaves your machine") if the gateway inherited it too. Every subprocess
# gets an explicit --host below so it can never fall back to that override.
LOCAL_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


class BridgeSession:
    def __init__(self, chat_id: str, cwd: Path):
        self.chat_id = chat_id
        self.cwd = cwd
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.ready = asyncio.Event()
        self.startup_error: str = ""
        self.model: str = ""
        self.awaiting_answer = False
        self.pending_job_id: str = ""
        self._pending_tool_names: dict = {}  # tool_call id -> tool name, to close its tag later
        self._reader_task: Optional[asyncio.Task] = None

    async def start(self, model: Optional[str] = None) -> None:
        if self.proc is not None and self.proc.returncode is None:
            return
        args = [sys.executable, "-m", _BRIDGE_MODULE, "--cwd", str(self.cwd), "--yolo",
                "--host", LOCAL_OLLAMA_HOST]
        if model:
            args += ["--model", model]
        self.proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _send(self, command: dict) -> None:
        if self.proc is None or self.proc.stdin is None or self.proc.returncode is not None:
            return
        self.proc.stdin.write((json.dumps(command) + "\n").encode("utf-8"))
        await self.proc.stdin.drain()

    async def dispatch(self, text: str) -> "jobs.Job":
        """Sends `text` either as a fresh prompt or, if this session has an
        unanswered ask_user question outstanding, as the answer to it -
        reusing the same job so its progress log keeps growing in place
        rather than starting a new bubble mid-question."""
        await asyncio.wait_for(self.ready.wait(), timeout=30)
        if self.startup_error:
            job = jobs.create(self.chat_id, user_text=text)
            jobs.fail(job.id, self.startup_error)
            return job

        if self.awaiting_answer and self.pending_job_id and jobs.get(self.pending_job_id):
            job = jobs.get(self.pending_job_id)
            job.status = "running"
            self.awaiting_answer = False
            await self._send({"type": "answer_question", "answer": text})
            return job

        job = jobs.create(self.chat_id, user_text=text)
        await self._send({"type": "send_message", "text": text, "turn_id": job.id})
        return job

    async def _read_loop(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        try:
            async for raw in self.proc.stdout:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._handle_event(event)
        except Exception:
            pass
        finally:
            if not self.ready.is_set():
                self.startup_error = "the local agent process exited before starting up"
                self.ready.set()
            self._fail_in_flight_job("the local agent process exited unexpectedly")

    def _fail_in_flight_job(self, message: str) -> None:
        job = jobs.latest_job_for_chat(self.chat_id)
        if job is not None and job.status == "running":
            jobs.fail(job.id, message)

    def _handle_event(self, event: dict) -> None:
        etype = event.get("type")

        if etype == "ready":
            self.model = event.get("model", "")
            if not event.get("ollama_reachable", True):
                self.startup_error = (
                    f"Ollama isn't reachable at {event.get('ollama_host', 'the configured host')}. "
                    "Start it with `ollama serve` and try again."
                )
            self.ready.set()
            return
        if etype == "fatal":
            self.startup_error = event.get("message", "the local agent failed to start")
            self.ready.set()
            return
        if etype in ("ollama_unreachable",):
            self.startup_error = (
                f"Ollama isn't reachable at {event.get('host', 'the configured host')}. "
                "Start it with `ollama serve` and try again."
            )
            return

        turn_id = event.get("turn_id") or self.pending_job_id
        job = jobs.get(turn_id) if turn_id else None

        if etype == "tool_call":
            name = event.get("name", "")
            args = event.get("args") or {}
            self._pending_tool_names[event.get("id")] = name
            if job:
                jobs.append_progress(job.id, tags.tool_call_open(name, args))

        elif etype == "tool_result":
            name = self._pending_tool_names.pop(event.get("id"), None)
            if job and name:
                jobs.append_progress(job.id, tags.tool_call_close(name))

        elif etype == "todo_update":
            marks = {"pending": "[ ]", "in_progress": "[ ]", "completed": "[x]"}
            text = "\n".join(f"- {marks.get(t.get('status', 'pending'), '[ ]')} {t.get('content', '')}"
                              for t in event.get("todos") or [])
            if job:
                jobs.append_progress(job.id, tags.roadmap_tag())
                jobs.set_roadmap(job.id, text)

        elif etype in ("assistant_final", "plan_proposal"):
            if job:
                jobs.complete(job.id, event.get("text", ""))
            self.awaiting_answer = False

        elif etype == "question_request":
            if job:
                block = tags.question_block(event.get("question", ""), event.get("options") or [])
                jobs.append_progress(job.id, block)
                jobs.complete(job.id, job.progress)
                self.awaiting_answer = True
                self.pending_job_id = job.id

        elif etype == "error":
            if job:
                jobs.fail(job.id, event.get("message", "an error occurred"))
            self.awaiting_answer = False

        elif etype == "interrupted":
            if job:
                jobs.fail(job.id, "interrupted")
            self.awaiting_answer = False


class BridgeManager:
    """One BridgeSession per chat, created lazily on first message."""

    def __init__(self):
        self._sessions: dict = {}

    async def get_or_create(self, chat_id: str, model: Optional[str] = None) -> BridgeSession:
        session = self._sessions.get(chat_id)
        if session is not None and session.proc is not None and session.proc.returncode is None:
            return session
        cwd = chats.workspace_dir(chat_id)
        session = BridgeSession(chat_id, cwd)
        self._sessions[chat_id] = session
        await session.start(model=model)
        return session

    def has_pending_question(self, chat_id: str) -> bool:
        session = self._sessions.get(chat_id)
        return bool(session and session.awaiting_answer)

    async def close(self, chat_id: str) -> None:
        session = self._sessions.pop(chat_id, None)
        if session is None or session.proc is None:
            return
        try:
            await session._send({"type": "shutdown"})
        except Exception:
            pass
        if session.proc.returncode is None:
            try:
                session.proc.terminate()
            except ProcessLookupError:
                pass

    async def close_all(self) -> None:
        for chat_id in list(self._sessions):
            await self.close(chat_id)


MANAGER = BridgeManager()
