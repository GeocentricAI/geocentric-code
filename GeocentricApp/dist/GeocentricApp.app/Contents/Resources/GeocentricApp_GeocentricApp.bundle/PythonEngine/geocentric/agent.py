"""The agentic tool-calling loop."""
from __future__ import annotations

import json
import platform as platform_mod
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from . import prompts
from . import session as session_mod
from . import tools as tools_mod
from .config import EFFORT_PROFILES, think_value_for_model
from .context import (
    ContextBudget,
    build_mention_block,
    context_length_for,
    estimate_messages_tokens,
    expand_mentions,
    load_project_context,
    resolve_window,
)
from .ollama_client import ChatResult, OllamaClient, OllamaConnectionError, OllamaError
from .permissions import PermissionManager
from .safety import PathRefused, WorkspaceGuard, assess_command
from .tools.base import ToolResult
from .tools.todo import STORE as TODO_STORE
from .ui.render import (
    AssistantStream,
    ToolCallView,
    render_auto_compacted,
    render_error,
    render_final_answer,
    render_hallucinated_tool_warning,
    render_interrupted,
    render_plan_blocked,
    render_stats,
    render_todos,
    render_warning,
)

MAX_TOOL_ITERATIONS = 40
MAX_PARALLEL_TOOLS = 4
RETRYABLE_ATTEMPTS = 2

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

# Models pretrained on tool-use data often free-run through an entire fake tool call *and*
# a fabricated result. We intercept the recognized dialects (below), but keep these markers
# as a backstop so anything we can't parse is at least flagged as untrustworthy.
_HALLUCINATED_TOOL_MARKERS = (
    "<｜tool", "<tool_call>", "<tool_response>", "<｜tool▁outputs｜>", "<|tool_call|>",
)


def looks_like_hallucinated_tool_use(content: str) -> bool:
    return any(marker in content for marker in _HALLUCINATED_TOOL_MARKERS)


def _extract_balanced_json_objects(text: str) -> list:
    objs, depth, start = [], 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    objs.append(text[start: i + 1])
                    start = None
    return objs


def parse_fallback_tool_calls(content: str) -> Optional[list]:
    """Recover tool calls from models that print JSON instead of using structured calls.

    Deliberately conservative: bails out unless essentially the whole message is such
    JSON naming real tools, so prose that merely contains a JSON example is never
    mistaken for an actual call.
    """
    text = _FENCE_RE.sub("", content).strip()
    if not text or "{" not in text:
        return None

    raw_objs = _extract_balanced_json_objects(text)
    if not raw_objs:
        return None

    non_ws_len = len(re.sub(r"\s", "", text))
    matched_len = sum(len(o) for o in raw_objs)
    if matched_len < non_ws_len * 0.9:
        return None

    calls = []
    for raw in raw_objs:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None
        name, arguments = None, None
        if "name" in obj and "arguments" in obj:
            name, arguments = obj.get("name"), obj.get("arguments")
        elif isinstance(obj.get("function"), dict):
            name, arguments = obj["function"].get("name"), obj["function"].get("arguments")
        elif "tool" in obj and "arguments" in obj:
            name, arguments = obj.get("tool"), obj.get("arguments")
        if not name or name not in tools_mod.TOOLS or not isinstance(arguments, dict):
            return None
        calls.append({"function": {"name": name, "arguments": arguments}})
    return calls or None


def _extract_deepseek_call(match):
    name = match.group(1).strip()
    try:
        return name, json.loads(match.group(2))
    except json.JSONDecodeError:
        return None, None


def _extract_hermes_call(match):
    try:
        obj = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None, None
    if not isinstance(obj, dict):
        return None, None
    if "name" in obj and "arguments" in obj:
        return obj.get("name"), obj.get("arguments")
    fn = obj.get("function")
    if isinstance(fn, dict):
        return fn.get("name"), fn.get("arguments")
    return None, None


# (end_marker, pattern, extractor). The cheap end_marker check runs against the growing
# buffer on every token so we can stop generation the instant a call completes.
_NATIVE_DIALECTS = [
    (
        "<｜tool▁call▁end｜>",
        re.compile(
            r"<｜tool▁call▁begin｜>\s*function\s*<｜tool▁sep｜>\s*([^\n<]+?)\s*"
            r"(\{.*?\})\s*(?:```)?\s*<｜tool▁call▁end｜>",
            re.DOTALL,
        ),
        _extract_deepseek_call,
    ),
    (
        "</tool_call>",
        re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL),
        _extract_hermes_call,
    ),
]


def try_parse_native_dialect(content: str) -> Optional[list]:
    """Detect a *complete* tool call in a model's own pretrained dialect.

    Only matches once the dialect's end marker has appeared, so this is safe to call on
    a partial buffer mid-stream - it returns None until the block is actually finished.
    """
    for end_marker, pattern, extractor in _NATIVE_DIALECTS:
        if end_marker not in content:
            continue
        m = pattern.search(content)
        if not m:
            continue
        name, arguments = extractor(m)
        if not name or not isinstance(arguments, dict) or name not in tools_mod.TOOLS:
            continue
        return [{"function": {"name": name, "arguments": arguments}}]
    return None


class Agent:
    def __init__(
        self,
        client: OllamaClient,
        model: str,
        permissions: PermissionManager,
        console,
        cwd: Optional[str] = None,
        extra_system: str = "",
        guard: Optional[WorkspaceGuard] = None,
        event_sink: Optional[Callable[[dict], None]] = None,
        workspace_mode: str = "code",
    ):
        self.client = client
        self.model = model
        self.permissions = permissions
        self.console = console
        self.cwd = Path(cwd) if cwd else Path.cwd()
        self.extra_system = extra_system
        self.workspace_mode = workspace_mode if workspace_mode in ("chat", "code", "work") else "code"
        # Event identity is assigned by Runner/GUI. The terminal client leaves it
        # empty, preserving its existing event-free behavior.
        self.current_turn_id: str = ""
        self.guard = guard or WorkspaceGuard(root=self.cwd)
        # Optional structured-event observer (used by the GUI bridge; a no-op for the
        # CLI). Never allowed to break the agent loop, hence the swallow-everything.
        self.event_sink = event_sink

        self.project_context = load_project_context(self.cwd)
        self.plan_mode = False
        self.last_plan_text = ""  # set when a plan-mode turn produces a proposal

        self._caps_cache: dict = {}
        self._window_cache: dict = {}
        self.budget = ContextBudget(window=self.context_window())
        self.messages: list = [{"role": "system", "content": self._system_prompt()}]

        self.last_result: Optional[ChatResult] = None
        self.generating: bool = False
        self._error_nudges: int = 0
        self.live_tokens: int = 0
        self.live_tps: float = 0.0
        self.current_tool: Optional[str] = None
        self.current_word: str = ""

        # Session totals, surfaced by /stats.
        self.turns = 0
        self.total_tokens = 0
        self.tool_calls = 0
        self.files_changed: set = set()
        self.started = time.time()

    def _emit(self, event: dict) -> None:
        if self.event_sink is not None:
            try:
                payload = dict(event)
                if self.current_turn_id and "turn_id" not in payload:
                    payload["turn_id"] = self.current_turn_id
                self.event_sink(payload)
            except Exception:
                pass

    # ------------------------------------------------------------------ prompt & caps

    def _git_branch(self) -> str:
        head = self.cwd / ".git" / "HEAD"
        try:
            text = head.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            return ""
        if text.startswith("ref: refs/heads/"):
            return text.split("refs/heads/", 1)[1]
        return text[:8]

    def _system_prompt(self, tools_supported: bool = True, effort_nudge: str = "") -> str:
        catalog = "" if tools_supported else prompts.format_tool_catalog(tools_mod.all_specs())
        return prompts.build_system_prompt(
            cwd=self.cwd,
            platform=f"{platform_mod.system()} {platform_mod.release()}",
            date=date.today().isoformat(),
            git_branch=self._git_branch(),
            project_context=self.project_context.text,
            plan_mode=self.plan_mode,
            tool_catalog=catalog,
            effort_nudge=effort_nudge,
            extra=self.extra_system,
            workspace_mode=self.workspace_mode,
        )

    def _capabilities(self, model: str):
        if model not in self._caps_cache:
            try:
                self._caps_cache[model] = self.client.get_capabilities(model)
            except (OllamaError, OllamaConnectionError):
                self._caps_cache[model] = None  # unknown; optimistic, runtime errors correct it
        return self._caps_cache[model]

    def _supports_tools(self, model: str) -> bool:
        caps = self._capabilities(model)
        return True if caps is None else "tools" in caps

    def _supports_thinking(self, model: str) -> bool:
        caps = self._capabilities(model)
        return True if caps is None else "thinking" in caps

    def model_max_context(self) -> int:
        """What the model itself supports, per its metadata."""
        if self.model not in self._window_cache:
            try:
                self._window_cache[self.model] = context_length_for(self.client.show(self.model))
            except (OllamaError, OllamaConnectionError):
                self._window_cache[self.model] = 0
        return self._window_cache[self.model]

    def context_window(self) -> int:
        """The window we actually request (and therefore actually get)."""
        return resolve_window(
            self.model_max_context(), getattr(self.permissions.config, "context_tokens", 0)
        )

    def refresh_budget(self) -> ContextBudget:
        self.budget.window = self.context_window()
        self.budget.used = estimate_messages_tokens(self.messages)
        return self.budget

    def _sync_system_prompt(self, tools_supported: bool, effort_nudge: str = "") -> None:
        desired = self._system_prompt(tools_supported, effort_nudge)
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = desired
        else:
            self.messages.insert(0, {"role": "system", "content": desired})

    # -------------------------------------------------------------------- conversation

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": self._system_prompt(self._supports_tools(self.model))}]
        TODO_STORE.clear()
        self.refresh_budget()

    def set_model(self, model: str) -> None:
        self.model = model
        self.budget.window = self.context_window()

    def set_workspace_mode(self, mode: str) -> None:
        """Switch the mode-specific contract without discarding the conversation."""
        if mode not in ("chat", "code", "work"):
            return
        self.workspace_mode = mode
        self._sync_system_prompt(self._supports_tools(self.model) and mode != "chat")

    def add_user_message(self, text: str) -> list:
        """Adds the message, expanding any @file mentions. Returns the mentions found."""
        _, mentions = expand_mentions(text, self.cwd)
        block = build_mention_block(mentions, self.cwd)
        content = f"{text}\n\n{block}" if block else text
        self.messages.append({"role": "user", "content": content})
        self.refresh_budget()
        return mentions

    def message_count(self) -> int:
        return len(self.messages)

    def compact(self, quiet: bool = False) -> bool:
        """Replace the transcript with a summary, freeing context."""
        if len(self.messages) <= 2:
            return False
        transcript = []
        for m in self.messages[1:]:
            role = m.get("role", "?")
            content = (m.get("content") or "")[:4000]
            if m.get("tool_calls"):
                content += f" [called: {', '.join(c.get('function', {}).get('name', '?') for c in m['tool_calls'])}]"
            transcript.append(f"{role}: {content}")

        try:
            result = self.client.stream_chat(
                self.model,
                [
                    {"role": "system", "content": prompts.COMPACT_INSTRUCTION},
                    {"role": "user", "content": "\n\n".join(transcript)[:60000]},
                ],
                tools=None,
            )
        except (OllamaError, OllamaConnectionError) as e:
            if not quiet:
                render_error(self.console, f"Compaction failed: {e}")
            return False

        self.messages = [
            {"role": "system", "content": self._system_prompt(self._supports_tools(self.model))},
            {"role": "user", "content": f"[Summary of the earlier part of this session]\n{result.content}"},
        ]
        self.refresh_budget()
        return True

    def _maybe_auto_compact(self, quiet: bool) -> None:
        self.refresh_budget()
        if not self.budget.should_compact:
            return
        before = self.budget.percent
        if self.compact(quiet=True):
            self.refresh_budget()
            render_auto_compacted(self.console, before, self.budget.percent)

    # ------------------------------------------------------------------------ the loop

    def run_turn(self, cancel_event=None, quiet: bool = False):
        """Run until the assistant gives a final answer with no further tool calls."""
        self.turns += 1
        # Small local models sometimes see a tool error (e.g. read_file on a
        # directory) and just give up - answering nothing useful instead of
        # retrying with the hinted fix. A couple of nudges per turn catches
        # that dead end and pushes the model to actually act on the error
        # rather than let the turn quietly end on it; MAX_TOOL_ITERATIONS is
        # still the hard backstop if it never recovers.
        self._error_nudges = 0
        # Chat is deliberately tool-free. The model receives an explicit mode
        # contract and the runtime omits schemas so it cannot make accidental
        # project/file actions from an ordinary conversation.
        tools_supported = self._supports_tools(self.model) and self.workspace_mode != "chat"
        thinking_supported = self._supports_thinking(self.model)
        effort = getattr(self.permissions.config, "effort", "medium")
        profile = EFFORT_PROFILES.get(effort, EFFORT_PROFILES["medium"])
        self._sync_system_prompt(tools_supported, profile["nudge"])
        self._maybe_auto_compact(quiet)

        for _ in range(MAX_TOOL_ITERATIONS):
            if cancel_event is not None and cancel_event.is_set():
                render_interrupted(self.console)
                self._emit({"type": "interrupted"})
                self._emit({"type": "status", "state": "idle"})
                return None

            allowed = tools_mod.read_only_names() if self.plan_mode else None
            tools_schema = tools_mod.as_ollama_tools(allowed) if tools_supported else None
            think = think_value_for_model(effort, self.model) if thinking_supported else None
            # num_ctx must be sent explicitly - see context.OLLAMA_DEFAULT_NUM_CTX.
            options = {"num_predict": profile["num_predict"], "num_ctx": self.context_window()}

            stream = AssistantStream(self.console)
            stream.start()
            self.generating = True
            self.live_tokens = 0
            self.current_word = stream.word
            native_calls: list = []
            self._emit({"type": "status", "state": "thinking"})

            def on_chunk(chunk):
                stream.feed(chunk.content_delta)
                stream.feed_thinking(chunk.thinking_delta)
                self.live_tokens = stream.tokens
                self.live_tps = stream.tokens_per_second
                if chunk.content_delta:
                    self._emit({"type": "assistant_delta", "text": chunk.content_delta})
                if chunk.thinking_delta:
                    self._emit({"type": "thinking_delta", "text": chunk.thinking_delta})
                if not native_calls and chunk.content_delta:
                    found = try_parse_native_dialect(stream.content)
                    if found:
                        native_calls.extend(found)
                        return True  # stop before it fabricates a result
                return False

            try:
                result = self._stream_with_retry(
                    tools_schema, on_chunk, options, think, cancel_event
                )
            except _ToolsUnsupported:
                self._caps_cache[self.model] = [
                    c for c in (self._caps_cache.get(self.model) or []) if c != "tools"
                ]
                tools_supported = False
                self._sync_system_prompt(False, profile["nudge"])
                stream.stop()
                self.generating = False
                continue
            except _ThinkingUnsupported:
                thinking_supported = False
                stream.stop()
                self.generating = False
                continue
            except (OllamaError, OllamaConnectionError) as e:
                stream.stop()
                self.generating = False
                render_error(self.console, str(e))
                self._emit({"type": "error", "message": str(e)})
                self._emit({"type": "status", "state": "idle"})
                return None
            finally:
                stream.stop()
                self.generating = False

            self.last_result = result
            self.total_tokens += result.eval_count or stream.tokens

            if result.cancelled:
                render_interrupted(self.console)
                self._emit({"type": "interrupted"})
                self._emit({"type": "status", "state": "idle"})
                return None

            tool_calls = result.tool_calls
            history_content = result.content
            if native_calls:
                tool_calls, history_content = native_calls, ""
            elif tools_supported and not tool_calls:
                fallback = parse_fallback_tool_calls(result.content)
                if fallback:
                    tool_calls, history_content = fallback, ""

            assistant_msg = {"role": "assistant", "content": history_content}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            self.messages.append(assistant_msg)

            if not tool_calls:
                if not self.plan_mode and self._error_nudges < 2 and self._last_message_was_tool_error():
                    self._error_nudges += 1
                    self.messages.append({
                        "role": "user",
                        "content": (
                            "That was a tool error, not a completed answer - don't stop here. "
                            "Retry with the fix the error suggested (e.g. list_dir instead of "
                            "read_file for a directory), or if you're genuinely stuck, say so "
                            "and explain what you tried."
                        ),
                    })
                    continue
                if looks_like_hallucinated_tool_use(result.content):
                    render_hallucinated_tool_warning(self.console)
                if self.plan_mode:
                    # Held for the REPL to render as a structured plan and act on.
                    self.last_plan_text = result.content
                    budget = self.refresh_budget()
                    render_stats(self.console, result, budget)
                    self._emit({"type": "plan_proposal", "text": result.content})
                    self._emit(self._stats_event(result, budget))
                    self._emit({"type": "status", "state": "idle"})
                    return result.content
                render_final_answer(self.console, result.content)
                budget = self.refresh_budget()
                render_stats(self.console, result, budget)
                self._emit({"type": "assistant_final", "text": result.content})
                self._emit(self._stats_event(result, budget))
                self._emit({"type": "status", "state": "idle"})
                return result.content

            self._execute_batch(tool_calls, cancel_event, quiet)
            if cancel_event is not None and cancel_event.is_set():
                render_interrupted(self.console)
                self._emit({"type": "interrupted"})
                self._emit({"type": "status", "state": "idle"})
                return None
            self._maybe_auto_compact(quiet)

        render_error(self.console, f"Stopped after {MAX_TOOL_ITERATIONS} tool steps without finishing.")
        self._emit({"type": "error", "message": f"Stopped after {MAX_TOOL_ITERATIONS} tool steps without finishing."})
        self._emit({"type": "status", "state": "idle"})
        return None

    def _stats_event(self, result, budget) -> dict:
        return {
            "type": "stats",
            "turns": self.turns,
            "total_tokens": self.total_tokens,
            "tool_calls": self.tool_calls,
            "tokens_per_second": getattr(result, "tokens_per_second", None),
            "context_used": budget.used,
            "context_window": budget.window,
            "context_percent": budget.percent,
        }

    def _stream_with_retry(self, tools_schema, on_chunk, options, think, cancel_event) -> ChatResult:
        """One model call, with a retry for transient failures.

        Capability mismatches are raised as distinct exceptions rather than retried,
        since the caller has to change the request shape before trying again.
        """
        last_error = None
        for attempt in range(RETRYABLE_ATTEMPTS):
            try:
                return self.client.stream_chat(
                    self.model,
                    self.messages,
                    tools=tools_schema,
                    on_chunk=on_chunk,
                    options=options,
                    think=think,
                    cancel_event=cancel_event,
                )
            except OllamaError as e:
                msg = str(e)
                if "does not support tools" in msg:
                    raise _ToolsUnsupported() from e
                if "does not support thinking" in msg:
                    raise _ThinkingUnsupported() from e
                last_error = e
                transient = any(s in msg.lower() for s in ("timeout", "connection reset", "temporarily", "503", "502"))
                if not transient or attempt == RETRYABLE_ATTEMPTS - 1:
                    raise
                time.sleep(1.0 + attempt)
        raise last_error  # unreachable, but keeps the contract explicit

    # ------------------------------------------------------------------ tool execution

    def _execute_batch(self, tool_calls: list, cancel_event, quiet: bool) -> None:
        """Run a batch of tool calls, in parallel when they're all read-only.

        Parallelism is restricted to tools declared concurrent_safe: running two writes
        at once risks interleaved edits to the same file, and running a write next to a
        read makes the read's result depend on timing. Reads have neither problem, and
        they're exactly the case where models batch calls anyway.
        """
        parsed = [self._parse_call(c) for c in tool_calls]
        parsed = [p for p in parsed if p is not None]
        if not parsed:
            return

        specs = [tools_mod.get_tool(name) for name, _ in parsed]
        all_parallel = len(parsed) > 1 and all(s is not None and s.concurrent_safe for s in specs)

        if all_parallel:
            call_ids = [uuid.uuid4().hex[:8] for _ in parsed]
            for cid, (name, args) in zip(call_ids, parsed):
                self._emit({"type": "tool_call", "id": cid, "name": name, "args": args})
            views = [ToolCallView(self.console, name, args, "low", quiet=quiet).start()
                     for name, args in parsed]
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_TOOLS) as pool:
                futures = [pool.submit(self._invoke, tools_mod.get_tool(n), a) for n, a in parsed]
                results = [f.result() for f in futures]
            for view, (name, args), res, cid in zip(views, parsed, results, call_ids):
                view.finish(res)
                self._record_result(name, args, res, call_id=cid)
            return

        for name, args in parsed:
            if cancel_event is not None and cancel_event.is_set():
                return
            self._execute_one(name, args, quiet)

    def _parse_call(self, call: dict):
        fn = call.get("function", {}) or {}
        name = fn.get("name")
        raw_args = fn.get("arguments", {})
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError:
                args = {}
        else:
            args = raw_args or {}
        if not name:
            return None
        return name, (args if isinstance(args, dict) else {})

    def _invoke(self, spec, args: dict) -> ToolResult:
        try:
            return spec.fn(**args)
        except TypeError as e:
            expected = ", ".join(spec.parameters.keys())
            return ToolResult(ok=False, error=f"Bad arguments for {spec.name}: {e}. Expected: {expected}")
        except Exception as e:
            return ToolResult(ok=False, error=f"{spec.name} raised {type(e).__name__}: {e}")

    def _execute_one(self, name: str, args: dict, quiet: bool) -> None:
        spec = tools_mod.get_tool(name)
        if spec is None:
            available = ", ".join(sorted(tools_mod.TOOLS))
            self.messages.append({
                "role": "tool",
                "content": f"ERROR: no tool named {name!r}. Available tools: {available}",
            })
            return

        if self.plan_mode and spec.mutating:
            render_plan_blocked(self.console, name)
            self.messages.append({
                "role": "tool",
                "content": (
                    f"BLOCKED: {name} cannot run in plan mode. Finish investigating and "
                    f"present your plan; the user will approve it before anything executes."
                ),
            })
            return

        gate = self._safety_gate(name, args)
        if gate is not None:
            self.messages.append({"role": "tool", "content": gate})
            return

        if spec.mutating:
            risk = assess_command(args.get("command", "")) if name == "run_command" else None
            danger = risk.level if risk and risk.level != "low" else spec.danger
            reasons = risk.reasons if risk else []
            force = bool(risk and risk.bypasses_auto_accept)
            if not self.permissions.request(name, args, danger, reasons=reasons, force_prompt=force):
                self.messages.append({
                    "role": "tool",
                    "content": f"DENIED: the user declined to run {name}. Do not retry it; ask how to proceed.",
                })
                return

        self.current_tool = name
        call_id = uuid.uuid4().hex[:8]
        self._emit({"type": "tool_call", "id": call_id, "name": name, "args": args})
        self._emit({"type": "status", "state": "tool_running"})
        view = ToolCallView(self.console, name, args, spec.danger, quiet=quiet).start()
        result = self._invoke(spec, args)
        view.finish(result)
        self.current_tool = None
        self._record_result(name, args, result, call_id=call_id)

    def _safety_gate(self, name: str, args: dict) -> Optional[str]:
        """Returns an error string to feed back to the model, or None to proceed."""
        path_arg = args.get("path")
        if not path_arg or name not in ("write_file", "edit_file", "multi_edit"):
            return None
        try:
            _, needs_approval, reason = self.guard.check_write(str(path_arg))
        except PathRefused as e:
            render_warning(self.console, f"refused: {e}")
            return f"REFUSED: {e}"
        if needs_approval:
            if not self.permissions.request(
                name, args, "high", reasons=[reason], force_prompt=True
            ):
                return f"DENIED: the user declined to write {path_arg} ({reason})."
        return None

    def _record_result(self, name: str, args: dict, result: ToolResult, call_id: str = "") -> None:
        self.tool_calls += 1

        if result.ok and name in ("write_file", "edit_file", "multi_edit") and "old_text" in result.meta:
            path = result.meta.get("path", args.get("path", ""))
            self.files_changed.add(path)
            session_mod.record_edit(
                self.cwd, path, result.meta["old_text"], result.meta.get("existed", True)
            )

        if result.ok and result.meta.get("todo_update"):
            render_todos(self.console, TODO_STORE)
            self._emit({
                "type": "todo_update",
                "todos": [{"content": t.content, "status": t.status} for t in TODO_STORE.items],
                "summary": TODO_STORE.summary_line(),
            })

        self._emit({
            "type": "tool_result",
            "id": call_id,
            "name": name,
            "ok": result.ok,
            "output": result.output if result.ok else result.error,
            "diff": result.diff,
            "meta": result.meta,
        })

        content = result.output if result.ok else f"ERROR: {result.error}"
        self.messages.append({"role": "tool", "content": tools_mod.truncate_output(content, limit=8000)})

    def _last_message_was_tool_error(self) -> bool:
        """True when the message just before the assistant's current (empty)
        reply was a failed tool result - i.e. the model had an error sitting
        right in front of it and still didn't act on it."""
        if len(self.messages) < 2:
            return False
        prior = self.messages[-2]
        return prior.get("role") == "tool" and str(prior.get("content", "")).startswith("ERROR:")


class _ToolsUnsupported(Exception):
    """The server rejected the request because this model has no tool support."""


class _ThinkingUnsupported(Exception):
    """The server rejected the request because this model has no thinking support."""
