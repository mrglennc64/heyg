"""Mock gateway for local frontend/CLI development — no Docker, no GPU.

Validates requests against the REAL gateway schema (so the contract is
exercised), keeps an in-memory avatar/voice registry, and simulates the job
lifecycle on a timer:
    queued -> synthesizing -> rendering -> compositing -> completed

Run:  python tools/dev_server.py [port]        (default 8000)

Accepts any non-empty X-Api-Key. Completed jobs return a placeholder
video_url — no actual video is rendered without the GPU workers.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "gateway"))
sys.path.insert(0, str(ROOT / "shared"))

import uvicorn
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import JobAccepted, JobStatus, VideoRequest  # real schemas

app = FastAPI(title="AvatarForge DEV MOCK gateway")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

JOBS: dict[str, tuple[float, VideoRequest]] = {}
AVATARS: list[dict] = [  # seeded so the editor has something to pick
    {"avatar_id": "demo-avatar-01", "name": "Demo — Glenn (base video)", "kind": "base_video"},
    {"avatar_id": "demo-avatar-02", "name": "Demo — Portrait", "kind": "still_portrait"},
]
VOICES: list[dict] = [
    {"voice_id": "demo-voice-01", "name": "Demo — Glenn (cloned)"},
]

STAGES = [("queued", 3), ("synthesizing", 6), ("rendering", 8), ("compositing", 4)]
TOTAL = sum(s for _, s in STAGES)
PROGRESS = {"queued": 0.0, "synthesizing": 0.2, "rendering": 0.5,
            "compositing": 0.85, "completed": 1.0}


def _require_key(x_api_key: str | None) -> None:
    if not x_api_key:
        raise HTTPException(401, "X-Api-Key header required (any value works in dev)")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "mode": "DEV MOCK — no GPU rendering"}


# ── assets ─────────────────────────────────────────────────────────
@app.get("/api/v1/avatars")
async def list_avatars(x_api_key: str | None = Header(None)):
    _require_key(x_api_key)
    return AVATARS


@app.post("/api/v1/avatars", status_code=201)
async def create_avatar(
    name: str = Form(...), kind: str = Form("base_video"),
    media: UploadFile = File(...), x_api_key: str | None = Header(None),
):
    _require_key(x_api_key)
    entry = {"avatar_id": uuid4().hex[:12], "name": name, "kind": kind}
    AVATARS.append(entry)
    return entry


@app.get("/api/v1/voices")
async def list_voices(x_api_key: str | None = Header(None)):
    _require_key(x_api_key)
    return VOICES


@app.post("/api/v1/voices", status_code=201)
async def create_voice(
    name: str = Form(...), sample: UploadFile = File(...),
    consent: UploadFile = File(...), x_api_key: str | None = Header(None),
):
    _require_key(x_api_key)
    entry = {"voice_id": uuid4().hex[:12], "name": name}
    VOICES.append(entry)
    return entry


# ── generation ─────────────────────────────────────────────────────
@app.post("/api/v1/generate-avatar-video", response_model=JobAccepted, status_code=202)
async def generate(req: VideoRequest, x_api_key: str | None = Header(None)):
    _require_key(x_api_key)
    job_id = uuid4().hex[:16]
    JOBS[job_id] = (time.monotonic(), req)
    return JobAccepted(job_id=job_id, status_url=f"/api/v1/jobs/{job_id}")


@app.get("/api/v1/jobs/{job_id}", response_model=JobStatus)
async def status(job_id: str, x_api_key: str | None = Header(None)):
    _require_key(x_api_key)
    if job_id not in JOBS:
        raise HTTPException(404, "job not found")

    created, req = JOBS[job_id]
    elapsed = time.monotonic() - created

    if elapsed >= TOTAL:
        words = sum(len(s.voice.input_text.split()) for s in req.scenes)
        return JobStatus(
            job_id=job_id, status="completed", progress=1.0,
            duration_sec=round(words / 2.5, 1),
            video_url="https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/720/Big_Buck_Bunny_720_10s_1MB.mp4",
        )

    for name, secs in STAGES:
        if elapsed < secs:
            return JobStatus(job_id=job_id, status=name, progress=PROGRESS[name])  # type: ignore[arg-type]
        elapsed -= secs
    return JobStatus(job_id=job_id, status="compositing", progress=0.85)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print("-- AvatarForge DEV MOCK gateway --------------------------")
    print(f"   http://localhost:{port}  (docs at /docs)")
    print("   Real schema validation, simulated ~21 s job lifecycle.")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
