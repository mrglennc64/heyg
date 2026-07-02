"""AvatarForge BRIDGE gateway — runs on the VPS, forwards renders to the GPU pod.

Same public API as the demo gateway, but real: it stores uploaded avatars,
and on generate it POSTs the avatar video + script to the pod's render
service (reached over the reverse SSH tunnel at 127.0.0.1:POD_TUNNEL_PORT),
then serves the returned MP4.

Voice cloning (XTTS) is not wired yet — the scene's language picks an
edge-tts neural voice. That's the honest MVP; upgrade later.

Env:
    POD_RENDER_URL   default http://127.0.0.1:18000   (the tunnel)
    DATA_DIR         default /data
"""
from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

POD_RENDER_URL = os.environ.get("POD_RENDER_URL", "http://127.0.0.1:18000")
DATA = Path(os.environ.get("DATA_DIR", "/data"))
(DATA / "avatars").mkdir(parents=True, exist_ok=True)
(DATA / "outputs").mkdir(parents=True, exist_ok=True)

# scene language -> edge-tts neural voice
VOICE_BY_LANG = {
    "en": "en-US-JennyNeural", "es": "es-ES-ElviraNeural", "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural", "it": "it-IT-ElsaNeural", "pt": "pt-BR-FranciscaNeural",
    "nl": "nl-NL-ColetteNeural", "pl": "pl-PL-ZofiaNeural", "ru": "ru-RU-SvetlanaNeural",
    "tr": "tr-TR-EmelNeural", "ar": "ar-EG-SalmaNeural", "zh": "zh-CN-XiaoxiaoNeural",
    "ja": "ja-JP-NanamiNeural", "ko": "ko-KR-SunHiNeural", "hi": "hi-IN-SwaraNeural",
}

AVATARS: dict[str, dict] = {}
VOICES: list[dict] = [{"voice_id": "default", "name": "Default (edge-tts, per language)"}]
JOBS: dict[str, dict] = {}

app = FastAPI(title="AvatarForge BRIDGE gateway")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _key(x):
    if not x:
        raise HTTPException(401, "X-Api-Key required")


@app.get("/healthz")
async def healthz():
    pod = "down"
    try:
        r = httpx.get(f"{POD_RENDER_URL}/health", timeout=5)
        pod = r.json() if r.status_code == 200 else "down"
    except Exception:
        pass
    return {"ok": True, "mode": "BRIDGE", "pod": pod}


@app.get("/api/v1/avatars")
async def list_avatars(x_api_key: str | None = Header(None)):
    _key(x_api_key)
    return [{"avatar_id": a, "name": v["name"], "kind": v["kind"]} for a, v in AVATARS.items()]


@app.post("/api/v1/avatars", status_code=201)
async def create_avatar(name: str = Form(...), kind: str = Form("base_video"),
                        media: UploadFile = File(...), x_api_key: str | None = Header(None)):
    _key(x_api_key)
    aid = uuid.uuid4().hex[:12]
    ext = Path(media.filename or "f.mp4").suffix or ".mp4"
    path = DATA / "avatars" / f"{aid}{ext}"
    with path.open("wb") as f:
        f.write(await media.read())
    AVATARS[aid] = {"name": name, "kind": kind, "path": str(path)}
    return {"avatar_id": aid, "name": name, "kind": kind}


@app.get("/api/v1/voices")
async def list_voices(x_api_key: str | None = Header(None)):
    _key(x_api_key)
    return VOICES


@app.post("/api/v1/voices", status_code=201)
async def create_voice(name: str = Form(...), sample: UploadFile = File(...),
                       consent: UploadFile = File(...), x_api_key: str | None = Header(None)):
    _key(x_api_key)
    vid = uuid.uuid4().hex[:12]
    VOICES.append({"voice_id": vid, "name": name})
    return {"voice_id": vid, "name": name}


def _run_render(job_id: str, avatar_path: str, text: str, voice: str):
    JOBS[job_id]["status"] = "rendering"
    try:
        with open(avatar_path, "rb") as fh:
            r = httpx.post(
                f"{POD_RENDER_URL}/render",
                files={"face": (Path(avatar_path).name, fh, "application/octet-stream")},
                data={"text": text, "voice": voice},
                timeout=1200,
            )
        if r.status_code != 200:
            raise RuntimeError(f"pod render {r.status_code}: {r.text[:400]}")
        out = DATA / "outputs" / f"{job_id}.mp4"
        out.write_bytes(r.content)
        JOBS[job_id].update(status="completed", video_key=str(out))
    except Exception as e:  # noqa: BLE001
        JOBS[job_id].update(status="failed", error=str(e)[:500])


@app.post("/api/v1/generate-avatar-video", status_code=202)
async def generate(req: dict, x_api_key: str | None = Header(None)):
    _key(x_api_key)
    scenes = req.get("scenes") or []
    if not scenes:
        raise HTTPException(422, "no scenes")
    s0 = scenes[0]
    aid = s0["avatar"]["avatar_id"]
    if aid not in AVATARS:
        raise HTTPException(422, f"unknown avatar_id {aid} (register it first)")
    text = s0["voice"]["input_text"]
    lang = s0["voice"].get("language", "en")
    voice = VOICE_BY_LANG.get(lang, "en-US-JennyNeural")

    job_id = uuid.uuid4().hex[:16]
    JOBS[job_id] = {"status": "queued", "progress": 0.0}
    threading.Thread(target=_run_render,
                     args=(job_id, AVATARS[aid]["path"], text, voice), daemon=True).start()
    return {"job_id": job_id, "status": "queued", "status_url": f"/api/v1/jobs/{job_id}"}


@app.get("/api/v1/jobs/{job_id}")
async def job_status(job_id: str, x_api_key: str | None = Header(None)):
    _key(x_api_key)
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    prog = {"queued": 0.1, "rendering": 0.5, "completed": 1.0, "failed": 0.0}[j["status"]]
    url = f"/files/{job_id}.mp4" if j["status"] == "completed" else None
    return {"job_id": job_id, "status": j["status"], "progress": prog,
            "video_url": url, "error": j.get("error")}


@app.get("/files/{name}")
async def files(name: str):
    p = DATA / "outputs" / name
    if not p.exists():
        raise HTTPException(404, "not found")
    return FileResponse(p, media_type="video/mp4")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
