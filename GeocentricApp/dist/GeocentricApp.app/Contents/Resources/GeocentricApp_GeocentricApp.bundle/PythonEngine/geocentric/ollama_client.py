"""Thin client for the local Ollama HTTP API (streaming chat + tool calls)."""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

import requests


class OllamaError(RuntimeError):
    pass


class OllamaConnectionError(OllamaError):
    """Raised when the local Ollama daemon can't be reached at all."""


@dataclass
class ChatChunk:
    content_delta: str = ""
    thinking_delta: str = ""
    tool_calls: list = field(default_factory=list)
    done: bool = False
    done_reason: Optional[str] = None
    eval_count: int = 0
    eval_duration: int = 0  # nanoseconds
    prompt_eval_count: int = 0


@dataclass
class ChatResult:
    content: str
    tool_calls: list
    eval_count: int = 0
    eval_duration: int = 0
    prompt_eval_count: int = 0
    cancelled: bool = False

    @property
    def tokens_per_second(self) -> float:
        if self.eval_duration <= 0:
            return 0.0
        return self.eval_count / (self.eval_duration / 1e9)


class OllamaClient:
    def __init__(self, host: str = "http://localhost:11434", timeout: int = 600, api_key: Optional[str] = None):
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._show_cache: dict = {}
        self._headers: dict = {}
        if api_key:
            self.set_api_key(api_key)

    def set_api_key(self, api_key: Optional[str]) -> None:
        """Only needed against a remotely-hosted Ollama sitting behind auth (e.g. a
        reverse proxy) - a plain local `ollama serve` ignores the header entirely."""
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def _url(self, path: str) -> str:
        return f"{self.host}{path}"

    def ping(self) -> bool:
        try:
            r = requests.get(self._url("/api/version"), headers=self._headers, timeout=3)
            return r.ok
        except requests.RequestException:
            return False

    def list_models(self) -> list:
        try:
            r = requests.get(self._url("/api/tags"), headers=self._headers, timeout=10)
            r.raise_for_status()
        except requests.RequestException as e:
            raise OllamaConnectionError(
                f"Could not reach Ollama at {self.host} ({e}). Is `ollama serve` running?"
            ) from e
        return r.json().get("models", [])

    def show(self, model: str) -> dict:
        """Full /api/show payload for a model (capabilities, model_info, template, ...)."""
        if model in self._show_cache:
            return self._show_cache[model]
        try:
            r = requests.post(self._url("/api/show"), json={"model": model}, headers=self._headers, timeout=15)
            r.raise_for_status()
        except requests.RequestException as e:
            raise OllamaConnectionError(f"Could not reach Ollama at {self.host} ({e})") from e
        data = r.json()
        self._show_cache[model] = data
        return data

    def get_capabilities(self, model: str) -> list:
        """Capabilities Ollama reports for a model (e.g. ['completion', 'tools'])."""
        return self.show(model).get("capabilities", [])

    def stream_chat(
        self,
        model: str,
        messages: list,
        tools: Optional[list] = None,
        on_chunk: Optional[Callable[[ChatChunk], None]] = None,
        options: Optional[dict] = None,
        think=None,
        cancel_event: Optional[threading.Event] = None,
    ) -> ChatResult:
        """POST /api/chat with stream=True, accumulate into a ChatResult.

        Calls `on_chunk` for every NDJSON line so callers can render tokens live. If
        `cancel_event` is set while streaming, the connection is closed and the returned
        ChatResult has `cancelled=True` with whatever partial content arrived so far.
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        if options:
            payload["options"] = options
        if think is not None:
            payload["think"] = think

        try:
            resp = requests.post(
                self._url("/api/chat"), json=payload, headers=self._headers, stream=True, timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise OllamaConnectionError(
                f"Could not reach Ollama at {self.host}. Is `ollama serve` running?"
            ) from e
        except requests.exceptions.HTTPError as e:
            body = ""
            try:
                body = resp.text[:500]
            except Exception:
                pass
            raise OllamaError(f"Ollama returned {e}: {body}") from e

        content_parts = []
        tool_calls: list = []
        eval_count = eval_duration = prompt_eval_count = 0
        cancelled = False

        for line in resp.iter_lines():
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                resp.close()
                break
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if "error" in data:
                raise OllamaError(data["error"])

            msg = data.get("message") or {}
            delta = msg.get("content", "") or ""
            thinking_delta = msg.get("thinking", "") or ""
            chunk_tool_calls = msg.get("tool_calls") or []
            done = bool(data.get("done"))

            if delta:
                content_parts.append(delta)
            if chunk_tool_calls:
                tool_calls.extend(chunk_tool_calls)
            if done:
                eval_count = data.get("eval_count", 0)
                eval_duration = data.get("eval_duration", 0)
                prompt_eval_count = data.get("prompt_eval_count", 0)

            if on_chunk:
                # If on_chunk returns truthy, the caller has seen enough (e.g. it spotted
                # a complete tool call in a model's own pretrained format) and wants the
                # connection closed now rather than letting the model keep generating -
                # notably, keep it from free-running into a fabricated "tool result".
                stop_now = on_chunk(
                    ChatChunk(
                        content_delta=delta,
                        thinking_delta=thinking_delta,
                        tool_calls=chunk_tool_calls,
                        done=done,
                        done_reason=data.get("done_reason"),
                        eval_count=data.get("eval_count", 0),
                        eval_duration=data.get("eval_duration", 0),
                        prompt_eval_count=data.get("prompt_eval_count", 0),
                    )
                )
                if stop_now:
                    resp.close()
                    break

        return ChatResult(
            content="".join(content_parts),
            tool_calls=tool_calls,
            eval_count=eval_count,
            eval_duration=eval_duration,
            prompt_eval_count=prompt_eval_count,
            cancelled=cancelled,
        )
