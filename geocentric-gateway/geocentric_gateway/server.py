"""FastAPI app implementing the API surface web/index.html already expects
(see the `API` object and its literal "/api/..." calls there). Agentic
(file/shell/git/workspace) turns run through bridge.py's gui_bridge
subprocess; casual replies go straight to Ollama via quickchat.py.
"""
from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from geocentric.ollama_client import OllamaConnectionError, OllamaClient

from . import auth, bridge, chats, cron, jobs, quickchat, skills
from .bridge import LOCAL_OLLAMA_HOST

WEB_DIR = Path(__file__).resolve().parent / "web"

app = FastAPI(title="Geocentric Gateway")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
async def _on_startup() -> None:
    cron.start(asyncio.get_event_loop())


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    cron.stop()
    await bridge.MANAGER.close_all()


def _ollama_client() -> OllamaClient:
    # No api_key - see bridge.py's LOCAL_OLLAMA_HOST docstring: this app never
    # talks to anything but the local daemon, on purpose.
    return OllamaClient(host=LOCAL_OLLAMA_HOST)


# --------------------------------------------------------------------- static

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/appicon.png")
async def appicon() -> FileResponse:
    return FileResponse(WEB_DIR / "appicon.png")


# ----------------------------------------------------------------------- auth

@app.post("/api/auth/login")
async def login(request: Request):
    body = await request.json()
    return auth.login(body)


@app.post("/api/auth/signup")
async def signup(request: Request):
    body = await request.json()
    return auth.signup(body)


@app.post("/api/auth/logout")
async def logout():
    return {"ok": True}


# --------------------------------------------------------------------- models

@app.get("/api/v1/models")
async def list_models():
    try:
        models = _ollama_client().list_models()
    except OllamaConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    ids = [m.get("name") or m.get("model") for m in models if m.get("name") or m.get("model")]
    return {"data": [{"id": i, "object": "model"} for i in ids]}


# ---------------------------------------------------------------------- chats

@app.get("/api/chats")
async def get_chats():
    return {"chats": chats.list_chats()}


@app.post("/api/chats")
async def save_chat(request: Request):
    body = await request.json()
    if not body.get("id"):
        raise HTTPException(status_code=400, detail="chat needs an 'id'")
    return chats.upsert_chat(body)


@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str):
    await bridge.MANAGER.close(chat_id)
    chats.delete_chat(chat_id)
    return {"ok": True}


# ----------------------------------------------------------------------- chat

@app.post("/api/chat")
async def quick_chat(request: Request):
    payload = await request.json()
    chat_id = payload.get("conversationId") or ""

    if chat_id and bridge.MANAGER.has_pending_question(chat_id):
        # An ask_user question is outstanding for this chat - route the reply
        # as its answer through the agent instead of a stateless quick chat.
        session = await bridge.MANAGER.get_or_create(chat_id)
        text = _last_user_text(payload)
        job = await session.dispatch(text)
        while job.status == "running":
            await asyncio.sleep(0.3)
        jobs.persist_turn(job)
        return JSONResponse({"reply": job.reply})

    return StreamingResponse(
        quickchat.stream_reply(payload, LOCAL_OLLAMA_HOST), media_type="text/event-stream"
    )


def _last_user_text(payload: dict) -> str:
    for m in reversed(payload.get("messages") or []):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


@app.post("/api/chat/jobs")
async def create_job(request: Request):
    payload = await request.json()
    chat_id = payload.get("conversationId") or ""
    if not chat_id:
        raise HTTPException(status_code=400, detail="conversationId is required")
    model = payload.get("model") or None
    text = _last_user_text(payload)

    chats.upsert_chat({"id": chat_id, "model": model or ""})
    session = await bridge.MANAGER.get_or_create(chat_id, model=model)
    job = await session.dispatch(text)
    return jobs.as_created_dict(job)


@app.get("/api/chat/jobs")
async def list_jobs():
    # resumeAgentJobs() calls this bare (no id) once on page load to
    # reattach polling to anything still running after a refresh.
    return {"jobs": [jobs.as_poll_dict(j) for j in jobs.all_jobs()]}


@app.get("/api/chat/jobs/{job_id}")
async def get_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="no such job")
    jobs.persist_turn(job)
    return {"job": jobs.as_poll_dict(job)}


# ---------------------------------------------------------------- workspaces

@app.get("/api/workspaces/{chat_id}/roadmap")
async def get_roadmap(chat_id: str):
    return {"roadmap": jobs.roadmap_for_chat(chat_id)}


@app.get("/api/workspaces/{chat_id}/zip")
async def zip_workspace(chat_id: str):
    workspace = chats.workspace_dir(chat_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in workspace.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(workspace))
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{chat_id}.zip"'},
    )


@app.get("/api/download/{chat_id}/{file_path:path}")
async def download_file(chat_id: str, file_path: str):
    workspace = chats.workspace_dir(chat_id).resolve()
    target = (workspace / file_path).resolve()
    if workspace not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="no such file")
    return FileResponse(target, filename=target.name)


# --------------------------------------------------------------------- usage

@app.get("/api/usage")
async def usage():
    # Local models have no real quota - report generous static headroom so
    # the frontend's usage bars render without implying a limit that isn't real.
    return {
        "plan": "Local (Ollama)",
        "tokens": {"used": 0, "limit": 1_000_000},
        "images": {"used": 0, "limit": 1_000},
        "resets": "never - running locally",
    }


# -------------------------------------------------------------------- skills

@app.get("/api/skills")
async def get_skills():
    return {"skills": skills.list_skills()}


# ----------------------------------------------------------------- cron jobs

@app.get("/api/cron-jobs")
async def get_cron_jobs():
    return {"jobs": cron.list_jobs()}


@app.post("/api/cron-jobs")
async def create_cron_job(request: Request):
    body = await request.json()
    if not (body.get("prompt") or "").strip():
        raise HTTPException(status_code=400, detail="prompt is required")
    return cron.create_job(body)


@app.delete("/api/cron-jobs/{job_id}")
async def delete_cron_job(job_id: str):
    cron.delete_job(job_id)
    return {"ok": True}


# ----------------------------------------------------------- image generation

@app.api_route("/api/generate-image/stream", methods=["GET", "POST"])
async def generate_image_stream():
    async def _body():
        yield (
            'data: {"error": "Local image generation isn\'t wired up yet - Ollama '
            "doesn't serve image models. Hook up a local diffusion backend (e.g. "
            'ComfyUI or Automatic1111) to enable this."}\n\n'
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(_body(), media_type="text/event-stream")
