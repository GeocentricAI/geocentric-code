"""The non-agent chat path: casual/no-tools messages go straight to Ollama
and stream back as SSE, with no gui_bridge subprocess involved at all. The
frontend's shouldUseAgentJob() heuristic (index.html) decides client-side
whether a message needs the full agent - this module only ever sees the
messages it already decided don't.

SSE frame shape ({"content": ...} / {"reasoning": ...}) matches what
web/index.html's extractReply()/extractThinking() already know how to read
(see readSse() there) - no frontend changes needed.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import AsyncIterator

from geocentric.ollama_client import ChatChunk, OllamaClient, OllamaError

DEFAULT_MODEL = "qwen2.5-coder:14b"


def _build_messages(payload: dict) -> list:
    messages = []
    system_prompt = (payload.get("systemPrompt") or "").strip()
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for m in payload.get("messages") or []:
        role = m.get("role")
        content = m.get("content", "")
        if role in ("user", "assistant", "system") and content:
            messages.append({"role": role, "content": content})
    return messages


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def stream_reply(payload: dict, ollama_host: str) -> AsyncIterator[str]:
    model = payload.get("model") or DEFAULT_MODEL
    messages = _build_messages(payload)
    if not messages:
        yield _sse({"error": "no messages to send"})
        yield "data: [DONE]\n\n"
        return

    wants_thinking = (payload.get("modelMode") or payload.get("mode") or "thinking") == "thinking"

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    _DONE = object()

    def on_chunk(chunk: ChatChunk) -> bool:
        loop.call_soon_threadsafe(queue.put_nowait, chunk)
        return False

    def run() -> None:
        client = OllamaClient(host=ollama_host)
        think = None
        if wants_thinking:
            try:
                think = "thinking" in client.get_capabilities(model)
            except Exception:
                think = False  # unknown model / Ollama hiccup - degrade rather than fail the request
        try:
            client.stream_chat(model=model, messages=messages, on_chunk=on_chunk, think=think)
        except OllamaError as e:
            if think and "does not support thinking" in str(e):
                # Capability cache was stale/wrong - retry once without it rather
                # than surfacing an error for something the model can just do.
                try:
                    client.stream_chat(model=model, messages=messages, on_chunk=on_chunk, think=None)
                except Exception as e2:
                    loop.call_soon_threadsafe(queue.put_nowait, e2)
            else:
                loop.call_soon_threadsafe(queue.put_nowait, e)
        except Exception as e:  # surfaced to the browser as a chat bubble, not a 500
            loop.call_soon_threadsafe(queue.put_nowait, e)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    threading.Thread(target=run, daemon=True).start()

    while True:
        item = await queue.get()
        if item is _DONE:
            break
        if isinstance(item, Exception):
            yield _sse({"error": str(item)})
            break
        frame = {}
        if item.content_delta:
            frame["content"] = item.content_delta
        if item.thinking_delta:
            frame["reasoning"] = item.thinking_delta
        if frame:
            yield _sse(frame)

    yield "data: [DONE]\n\n"
