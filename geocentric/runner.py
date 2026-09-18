"""Runs agent turns on a background thread so the REPL prompt stays live and interruptible."""
from __future__ import annotations

import asyncio
import concurrent.futures
import queue
import threading
import uuid
from typing import Callable, Optional

from .permissions import Decision
from .ui.render import render_approval_needed, render_error, render_question_needed, render_queued


class Runner:
    """Owns a worker thread that drains a queue of user messages one at a time.

    Several things route through here rather than happening inline on the worker:
    - cancellation (^C sets `cancel`, which agent.run_turn polls)
    - approval prompts (the worker blocks on `_approval_event`; the main thread answers
      via /approve, /deny, /always) - Rich's blocking input() must not run on a thread
      other than the one prompt_toolkit's Application owns
    - ask_user questions: rendered as a real arrow-key picker by scheduling a coroutine
      onto the main thread's live event loop (see ask_questions); falls back to a typed
      /answer flow if that loop isn't available for some reason

    `loop_holder` is a dict the main thread updates every time it starts a new
    prompt_session.prompt() call (via its pre_run hook) - see cli.py. PromptSession.prompt()
    creates a *fresh* event loop on every single call (asyncio.run() under the hood, not a
    persistent loop), so "the loop" has to be captured freshly each time rather than once
    at startup.
    """

    def __init__(self, agent, console, on_idle: Optional[Callable] = None, loop_holder: Optional[dict] = None,
                 event_sink: Optional[Callable[[dict], None]] = None):
        self.agent = agent
        self.console = console
        self.on_idle = on_idle
        self.loop_holder = loop_holder if loop_holder is not None else {"loop": None}
        # Optional structured-event observer (used by the GUI bridge; a no-op for the CLI).
        self.event_sink = event_sink
        self.current_turn_id: str = ""
        self.busy = threading.Event()
        self.cancel = threading.Event()
        self.pending_approval: Optional[dict] = None
        self._approval_event = threading.Event()
        self._approval_decision = Decision.DENY
        self.pending_question: Optional[dict] = None  # only used by the text-fallback path
        self._question_event = threading.Event()
        self._question_answer = None
        self._queue: "queue.Queue" = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def submit(self, text: str, already_added: bool = False, turn_id: str = "") -> None:
        if self.busy.is_set():
            render_queued(self.console, text)
        self._queue.put((text, already_added, turn_id))

    def _emit(self, event: dict) -> None:
        if self.event_sink is None:
            return
        try:
            payload = dict(event)
            if self.current_turn_id and "turn_id" not in payload:
                payload["turn_id"] = self.current_turn_id
            self.event_sink(payload)
        except Exception:
            pass

    def interrupt(self) -> None:
        if self.busy.is_set():
            self.cancel.set()
        if self.pending_approval is not None:
            self._approval_decision = Decision.DENY
            self._approval_event.set()
        if self.pending_question is not None:
            self._question_answer = None
            self._question_event.set()

    def request_approval(self, tool_name: str, args: dict, danger: str, reasons=None) -> Decision:
        """Called from the worker thread. Blocks until the main thread answers, or ^C."""
        approval_id = uuid.uuid4().hex[:8]
        self.pending_approval = {"id": approval_id, "tool": tool_name, "args": args, "danger": danger}
        self._approval_event.clear()
        render_approval_needed(self.console, tool_name, args, danger, reasons or [])
        self._emit({
            "type": "approval_request", "id": approval_id, "tool": tool_name,
            "args": args, "danger": danger, "reasons": reasons or [],
        })
        while not self._approval_event.wait(timeout=0.2):
            if self.cancel.is_set():
                self.pending_approval = None
                return Decision.DENY
        self.pending_approval = None
        self._emit({"type": "approval_resolved", "id": approval_id, "decision": self._approval_decision.value})
        return self._approval_decision

    def answer_approval(self, decision: Decision) -> bool:
        if self.pending_approval is None:
            return False
        self._approval_decision = decision
        self._approval_event.set()
        return True

    # ------------------------------------------------------------------ agent questions

    def ask_questions(self, items: list):
        """Called from the worker thread when the agent uses ask_user. `items` is
        [{"question", "options", "multi_select"}, ...] - one or several, presented as a
        short wizard. Returns a list of answers (str, or list[str] for multi_select
        items), or None if the user cancelled.

        Prefers a real arrow-key picker, rendered by scheduling a coroutine onto the
        main thread's currently-running event loop (captured via loop_holder - see the
        class docstring). Verified in a pty harness: prompt_toolkit's `in_terminal()`
        detaches the live input prompt, the nested picker Application owns the terminal
        exclusively while it runs, and the outer prompt resumes cleanly afterward - the
        two never run concurrently despite living on different threads.

        Falls back to a plain print + typed /answer flow if no loop is available (e.g.
        called in the sliver of time between one prompt() and the next) - the same
        proven-safe pattern used for tool approvals, just slower to use.
        """
        loop = self.loop_holder.get("loop")
        if loop is not None and loop.is_running():
            try:
                return self._ask_via_picker(items, loop)
            except Exception:
                pass  # fall through to the text flow below
        return self._ask_via_text(items)

    def _ask_via_picker(self, items: list, loop) -> Optional[list]:
        from prompt_toolkit.application.run_in_terminal import in_terminal

        from .ui.picker import select_many_async, select_one_async

        async def wizard():
            answers = []
            async with in_terminal():
                for i, item in enumerate(items):
                    label = item["question"]
                    if len(items) > 1:
                        label = f"({i + 1}/{len(items)}) {label}"
                    if item["multi_select"]:
                        ans = await select_many_async(label, item["options"], allow_cancel=True)
                    else:
                        ans = await select_one_async(label, item["options"], allow_cancel=True)
                    if ans is None:
                        return None  # cancelled partway through - abandon the whole wizard
                    answers.append(ans)
            return answers

        future = asyncio.run_coroutine_threadsafe(wizard(), loop)
        while True:
            try:
                return future.result(timeout=0.2)
            except concurrent.futures.TimeoutError:
                if self.cancel.is_set():
                    loop.call_soon_threadsafe(future.cancel)
                    return None

    def _ask_via_text(self, items: list) -> Optional[list]:
        answers = []
        for item in items:
            self.pending_question = item
            self._question_event.clear()
            render_question_needed(self.console, item["question"], item["options"], item["multi_select"])
            self._emit({
                "type": "question_request", "question": item["question"],
                "options": item["options"], "multi_select": item["multi_select"],
            })
            while not self._question_event.wait(timeout=0.2):
                if self.cancel.is_set():
                    self.pending_question = None
                    return None
            if self._question_answer is None:
                self.pending_question = None
                return None
            answers.append(self._question_answer)
        self.pending_question = None
        return answers

    def answer_question(self, answer) -> None:
        self._question_answer = answer
        self._question_event.set()

    def _loop(self) -> None:
        while True:
            try:
                self._process_one()
            except Exception:
                # Last resort: even a failure inside the error handler must not kill this
                # thread, or every later message would queue forever with nothing to run it.
                self.busy.clear()
                self.cancel.clear()

    def _process_one(self) -> None:
        text, already_added, turn_id = self._queue.get()
        self.current_turn_id = turn_id or ""
        self.agent.current_turn_id = self.current_turn_id
        self.cancel.clear()
        self.busy.set()
        self._emit({"type": "status", "state": "busy"})
        try:
            if not already_added:
                self.agent.add_user_message(text)
            self.agent.run_turn(cancel_event=self.cancel, quiet=True)
        except Exception as e:
            render_error(self.console, f"unexpected error: {type(e).__name__}: {e}")
            self._emit({"type": "error", "message": f"unexpected error: {type(e).__name__}: {e}"})
        finally:
            self.busy.clear()
            self.cancel.clear()
            self._emit({"type": "status", "state": "idle"})
            self.current_turn_id = ""
            self.agent.current_turn_id = ""
            if self.on_idle:
                try:
                    self.on_idle()
                except Exception:
                    pass
