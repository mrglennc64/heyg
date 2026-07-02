"""AvatarForge GPU render service — runs ON the RunPod pod.

POST /render  (multipart):
    face    : UploadFile   — a video (mp4) or portrait image
    text    : str          — what the avatar should say
    voice   : str          — edge-tts voice (default en-US-JennyNeural)
  → streams back the rendered talking-avatar MP4.

Pipeline: edge-tts (speech) → Wav2Lip (GPU lip-sync). Same engine we proved
in prove_render.sh. Voice cloning (XTTS) is a later upgrade; for now the
"voice" is an edge-tts neural voice picked per language.

Reachable from the VPS via a reverse SSH tunnel (see start_pod.sh), so no
RunPod port exposure / proxy-URL churn.
"""
from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

WAV2LIP = Path("/workspace/proof/Wav2Lip")
WORK = Path("/workspace/renders")
WORK.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AvatarForge GPU render service")


@app.get("/health")
def health():
    import torch
    return {"ok": True, "cuda": torch.cuda.is_available(),
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}


@app.post("/render")
async def render(
    face: UploadFile = File(...),
    text: str = Form(...),
    voice: str = Form("en-US-JennyNeural"),
):
    job = uuid.uuid4().hex[:12]
    d = WORK / job
    d.mkdir(parents=True, exist_ok=True)

    # 1. save uploaded face (video or image)
    suffix = Path(face.filename or "face.mp4").suffix or ".mp4"
    face_path = d / f"face{suffix}"
    with face_path.open("wb") as f:
        shutil.copyfileobj(face.file, f)

    # 2. speech via edge-tts
    mp3, wav = d / "speech.mp3", d / "speech.wav"
    try:
        subprocess.run(["python", "-m", "edge_tts", "--voice", voice,
                        "--text", text, "--write-media", str(mp3)],
                       check=True, capture_output=True, timeout=180)
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error",
                        "-i", str(mp3), "-ar", "16000", "-ac", "1", str(wav)],
                       check=True, capture_output=True, timeout=120)
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"tts failed: {e.stderr.decode()[:500]}")

    # 3. Wav2Lip lip-sync on GPU
    out = d / "avatar.mp4"
    try:
        subprocess.run(
            ["python", "inference.py",
             "--checkpoint_path", "checkpoints/wav2lip_gan.pth",
             "--face", str(face_path), "--audio", str(wav),
             "--outfile", str(out), "--pads", "0", "15", "0", "0", "--nosmooth"],
            check=True, capture_output=True, cwd=WAV2LIP, timeout=900,
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"render failed: {e.stderr.decode()[-800:]}")

    if not out.exists():
        raise HTTPException(500, "no output produced")
    return FileResponse(out, media_type="video/mp4", filename=f"avatar_{job}.mp4")
