"""AvatarForge BRIDGE gateway — runs on the VPS, forwards renders to the GPU pod.

Same public API as the demo gateway, but real: it stores uploaded avatars and
cloned-voice references (sample + consent), and on generate it POSTs the
avatar video + script — plus the voice reference when the scene uses a cloned
voice — to the pod's render service (reached over the reverse SSH tunnel at
127.0.0.1:POD_TUNNEL_PORT), then serves the returned MP4.

Cloned voices synthesize with Chatterbox on the pod; scenes without a cloned
voice fall back to an edge-tts neural voice picked per language.

Avatars and voices persist in DATA_DIR/registry.json so a service restart
doesn't lose them. Jobs stay in-memory (they're minutes-lived).

Env:
    POD_RENDER_URL   default http://127.0.0.1:18000   (the tunnel)
    DATA_DIR         default /data
"""
from __future__ import annotations

import json
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
(DATA / "voices").mkdir(parents=True, exist_ok=True)
(DATA / "outputs").mkdir(parents=True, exist_ok=True)
REGISTRY = DATA / "registry.json"

# scene language -> edge-tts neural voice (fallback when no cloned voice)
VOICE_BY_LANG = {
    "en": "en-US-JennyNeural", "es": "es-ES-ElviraNeural", "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural", "it": "it-IT-ElsaNeural", "pt": "pt-BR-FranciscaNeural",
    "nl": "nl-NL-ColetteNeural", "pl": "pl-PL-ZofiaNeural", "ru": "ru-RU-SvetlanaNeural",
    "tr": "tr-TR-EmelNeural", "ar": "ar-EG-SalmaNeural", "zh": "zh-CN-XiaoxiaoNeural",
    "ja": "ja-JP-NanamiNeural", "ko": "ko-KR-SunHiNeural", "hi": "hi-IN-SwaraNeural",
}

DEFAULT_VOICE = {"voice_id": "default", "name": "Default (edge-tts, per language)"}

AVATARS: dict[str, dict] = {}
VOICES: list[dict] = [DEFAULT_VOICE]
JOBS: dict[str, dict] = {}
_registry_lock = threading.Lock()


def _load_registry() -> None:
    if not REGISTRY.exists():
        return
    try:
        reg = json.loads(REGISTRY.read_text())
    except Exception as e:  # noqa: BLE001 — a corrupt registry shouldn't block boot
        print(f"[registry] unreadable, starting empty: {e}", flush=True)
        return
    AVATARS.update(reg.get("avatars", {}))
    VOICES.extend(v for v in reg.get("voices", []) if v.get("voice_id") != "default")


def _save_registry() -> None:
    with _registry_lock:
        tmp = REGISTRY.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "avatars": AVATARS,
            "voices": [v for v in VOICES if v.get("voice_id") != "default"],
        }, indent=2))
        tmp.replace(REGISTRY)


_load_registry()

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
    return {"ok": True, "mode": "BRIDGE", "pod": pod,
            "voices": len(VOICES) - 1, "avatars": len(AVATARS)}


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
    _save_registry()
    return {"avatar_id": aid, "name": name, "kind": kind}


@app.get("/api/v1/voices")
async def list_voices(x_api_key: str | None = Header(None)):
    _key(x_api_key)
    return [{k: v for k, v in rec.items() if not k.endswith("_path")} for rec in VOICES]


@app.post("/api/v1/voices", status_code=201)
async def create_voice(name: str = Form(...), sample: UploadFile = File(...),
                       consent: UploadFile = File(...), x_api_key: str | None = Header(None)):
    _key(x_api_key)
    vid = uuid.uuid4().hex[:12]
    vdir = DATA / "voices" / vid
    vdir.mkdir(parents=True, exist_ok=True)
    sample_path = vdir / f"sample{Path(sample.filename or 's.wav').suffix or '.wav'}"
    sample_path.write_bytes(await sample.read())
    consent_path = vdir / f"consent{Path(consent.filename or 'c.wav').suffix or '.wav'}"
    consent_path.write_bytes(await consent.read())
    VOICES.append({"voice_id": vid, "name": name, "cloned": True,
                   "sample_path": str(sample_path), "consent_path": str(consent_path)})
    _save_registry()
    return {"voice_id": vid, "name": name, "cloned": True}


def _run_render(job_id: str, avatar_path: str, text: str, voice: str,
                language: str, ref_path: str | None):
    JOBS[job_id]["status"] = "rendering"
    files = {}
    try:
        files["face"] = (Path(avatar_path).name,
                         open(avatar_path, "rb"), "application/octet-stream")
        if ref_path:
            files["ref_audio"] = (Path(ref_path).name,
                                  open(ref_path, "rb"), "application/octet-stream")
        r = httpx.post(
            f"{POD_RENDER_URL}/render",
            files=files,
            data={"text": text, "voice": voice, "language": language},
            timeout=1800,
        )
        if r.status_code != 200:
            raise RuntimeError(f"pod render {r.status_code}: {r.text[:400]}")
        out = DATA / "outputs" / f"{job_id}.mp4"
        out.write_bytes(r.content)
        JOBS[job_id].update(status="completed", video_key=str(out))
    except Exception as e:  # noqa: BLE001
        JOBS[job_id].update(status="failed", error=str(e)[:500])
    finally:
        for _name, fh, _ct in files.values():
            fh.close()


@app.post("/api/v1/generate-avatar-video", status_code=202)
async def generate(req: dict, x_api_key: str | None = Header(None)):
    _key(x_api_key)
    scenes = req.get("scenes") or []
    if not scenes:
        raise HTTPException(422, "no scenes")
    s0 = scenes[0] or {}
    avatar = s0.get("avatar") or {}
    voice_obj = s0.get("voice") or {}
    aid = avatar.get("avatar_id")
    print(f"[generate] payload scene0 avatar={avatar} voice_keys={list(voice_obj)}", flush=True)
    if not aid or aid not in AVATARS:
        raise HTTPException(422, f"unknown or missing avatar_id {aid!r} (register it first)")
    text = (voice_obj.get("input_text") or voice_obj.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "script text is empty — type what the avatar should say")
    lang = voice_obj.get("language") or "en"
    voice = VOICE_BY_LANG.get(lang, "en-US-JennyNeural")

    ref_path = None
    vid = voice_obj.get("voice_id")
    if vid and vid != "default":
        rec = next((v for v in VOICES if v["voice_id"] == vid), None)
        if rec is None:
            raise HTTPException(422, f"unknown voice_id {vid!r} (clone it first)")
        sp = rec.get("sample_path")
        if sp and Path(sp).exists():
            ref_path = sp
        else:
            print(f"[generate] voice {vid} has no sample on disk — edge-tts fallback", flush=True)

    job_id = uuid.uuid4().hex[:16]
    JOBS[job_id] = {"status": "queued", "progress": 0.0}
    threading.Thread(target=_run_render,
                     args=(job_id, AVATARS[aid]["path"], text, voice, lang, ref_path),
                     daemon=True).start()
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
