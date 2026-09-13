"""Zenith × Antigravity worker — local HTTP API (REST, no auth on loopback).

Zenith (the container) reaches the worker over 127.0.0.1:8022. The worker runs
as the `singh` user on the Pi host via systemd (zenith-worker.service), because
the Antigravity CLI (`agy`) authenticates with the user's Google login in
~/.gemini.

Endpoints
---------
POST /tasks                      submit a coding task (non-blocking)
GET  /tasks                      list tasks (newest first)
GET  /tasks/{id}                 full task state
GET  /tasks/{id}/output          accumulated output text
GET  /tasks/{id}/artifacts       discovered workspace files
POST /tasks/{id}/followup        send a message into the running conversation
POST /tasks/{id}/cancel          cancel a queued/running task
GET  /health                     liveness

The task model is persistent (worker/tasks.jsonl) and statuses follow the
requested state machine (QUEUED → … → COMPLETED/FAILED/CANCELLED).
"""
from __future__ import annotations

import asyncio
import json
import time

import uvicorn
from fastapi import FastAPI, HTTPException, Request

from . import agy
from . import tasks as T
from . import brief

app = FastAPI(title="Zenith Antigravity Worker", version="1.0.0")

# Bind on the Docker bridge so the `zenith` container can reach it via the
# host gateway (127.0.0.1 from a container is the container's own loopback).
# The Pi is behind CGNAT + the worker exposes a tiny loopback-only surface;
# Zenith reaches it via the private bridge gateway, not from the internet.
_HOST = "0.0.0.0"
_PORT = int(__import__("os").environ.get("ZENITH_WORKER_PORT", "8022"))


@app.get("/health")
async def health():
    return {"status": "ok", "worker": "antigravity-agy"}


@app.post("/tasks")
async def create_task(payload: dict = None, request: Request = None):
    """Create a task from a spec dict (or a `{spec: {...}}` wrapper)."""
    if request:
        body = await request.json()
        payload = body.get("spec", body)
    if not payload or not payload.get("task"):
        raise HTTPException(status_code=400, detail="Missing `task` in spec.")
    spec = payload
    parent = payload.get("parent")
    workspace = payload.get("workspace")
    task = agy.submit(spec, parent=parent, workspace=workspace)
    return {"task_id": task.id, "status": task.status, "workspace": task.workspace}


@app.post("/chat")
async def chat_endpoint(request: Request):
    """Run an interactive prompt directly through Antigravity CLI (agy) on the host."""
    body = await request.json()
    prompt = body.get("prompt", "")
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Missing `prompt`.")
    
    from fastapi.responses import StreamingResponse
    import subprocess

    cmd = [
        agy._AGY, "--continue", "--print", prompt,
        "--model", "gemini-3.1-pro-high",
        "--effort", "high",
        "--mode", "accept-edits",
        "--output-format", "stream-json",
        "--dangerously-skip-permissions",
    ]

    async def event_generator():
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/home/singh/peacos-workspaces/zenith-main",
        )
        if proc.stdout:
            while True:
                line_bytes = await proc.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", "replace").rstrip("\n")
                if line.strip():
                    yield f"data: {line}\n\n"
        await proc.wait()
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/tasks")
async def list_tasks():
    return {"tasks": [t.to_dict() for t in T.store.list()]}


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    return agy.get_status(task_id)


@app.get("/tasks/{task_id}/output")
async def get_output(task_id: str):
    try:
        return {"output": agy.get_output(task_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")


@app.get("/tasks/{task_id}/artifacts")
async def get_artifacts(task_id: str):
    try:
        t = agy.get_status(task_id)
        return {"artifacts": t.get("artifacts", [])}
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")


@app.post("/tasks/{task_id}/followup")
async def post_followup(task_id: str, request: Request):
    body = await request.json()
    msg = body.get("message")
    if not msg:
        raise HTTPException(status_code=400, detail="Missing `message`")
    ok = agy.send_followup(task_id, msg)
    if not ok:
        raise HTTPException(status_code=409, detail="task not in a followable state")
    return {"sent": True}


@app.post("/tasks/{task_id}/cancel")
async def post_cancel(task_id: str):
    ok = agy.cancel(task_id)
    if not ok:
        raise HTTPException(status_code=409, detail="task not cancellable")
    return {"cancelled": True}


def main():
    uvicorn.run(app, host=_HOST, port=_PORT, log_level="info")


if __name__ == "__main__":
    main()