"""AvatarForge GPU render service — runs ON the RunPod pod.

POST /render  (multipart):
    face      : UploadFile   — a video (mp4) or portrait image
    text      : str          — what the avatar should say
    voice     : str          — edge-tts voice (default en-US-JennyNeural)
    language  : str          — scene language code (default "en")
    ref_audio : UploadFile?  — optional cloned-voice reference sample; when
                               present, speech is synthesized with Chatterbox
                               Multilingual (zero-shot cloning), falling back
                               to edge-tts if the engine is unavailable.
  → streams back the rendered talking-avatar MP4.

Pipeline: Chatterbox or edge-tts (speech) → Wav2Lip (GPU lip-sync).

The cloning engine is isolated behind _synth_cloned() so an alternative
(e.g. k2-fsa OmniVoice) can be slotted in for an A/B without touching the
render flow.

Reachable from the VPS via a reverse SSH tunnel (see start_pod.sh), so no
RunPod port exposure / proxy-URL churn.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

WAV2LIP = Path("/workspace/proof/Wav2Lip")
WORK = Path("/workspace/renders")
WORK.mkdir(parents=True, exist_ok=True)

# Chatterbox Multilingual coverage; anything else clones in English prosody.
CHATTERBOX_LANGS = {
    "ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "it", "ja",
    "ko", "ms", "nl", "no", "pl", "pt", "ru", "sv", "sw", "tr", "zh",
}
_SENTENCE_RE = re.compile(r"(?<=[.!?…。！？])\s+")
MAX_CHUNK_CHARS = 280  # long-form stability: synthesize per sentence group

_clone_model = None
_clone_lock = threading.Lock()

# Probed at startup in a background thread; find_spec alone lies when the
# package is installed but its imports are broken (e.g. torch/torchvision
# version skew — seen live 2026-07-03).
CLONE_STATUS = {"engine": None}


def _probe_clone_engine() -> None:
    try:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # noqa: F401
        CLONE_STATUS["engine"] = "chatterbox"
    except Exception as e:  # noqa: BLE001
        CLONE_STATUS["engine"] = f"unavailable: {type(e).__name__}: {e}"[:200]


threading.Thread(target=_probe_clone_engine, daemon=True).start()

app = FastAPI(title="AvatarForge GPU render service")


def _chatterbox():
    global _clone_model
    with _clone_lock:
        if _clone_model is None:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            _clone_model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    return _clone_model


def _chunks(text: str) -> list[str]:
    parts: list[str] = []
    buf = ""
    for sent in _SENTENCE_RE.split(text.strip()):
        if buf and len(buf) + len(sent) + 1 > MAX_CHUNK_CHARS:
            parts.append(buf)
            buf = sent
        else:
            buf = f"{buf} {sent}".strip()
    if buf:
        parts.append(buf)
    return parts or [text]


def _synth_cloned(text: str, language: str, ref_path: Path, out_wav: Path) -> None:
    import torch
    import torchaudio

    model = _chatterbox()
    lang = language if language in CHATTERBOX_LANGS else "en"
    waves = [
        model.generate(chunk, language_id=lang, audio_prompt_path=str(ref_path))
        for chunk in _chunks(text)
    ]
    torchaudio.save(str(out_wav), torch.cat(waves, dim=-1).cpu(), model.sr)


@app.get("/health")
def health():
    import torch
    return {
        "ok": True,
        "cuda": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "clone_engine": CLONE_STATUS["engine"],
    }


@app.post("/render")
async def render(
    face: UploadFile = File(...),
    text: str = Form(...),
    voice: str = Form("en-US-JennyNeural"),
    language: str = Form("en"),
    ref_audio: UploadFile | None = File(None),
):
    job = uuid.uuid4().hex[:12]
    d = WORK / job
    d.mkdir(parents=True, exist_ok=True)

    # 1. save uploaded face (video or image)
    suffix = Path(face.filename or "face.mp4").suffix or ".mp4"
    face_path = d / f"face{suffix}"
    with face_path.open("wb") as f:
        shutil.copyfileobj(face.file, f)

    # 2. speech — cloned when a reference sample came along, else edge-tts
    wav = d / "speech.wav"
    cloned = False
    if ref_audio is not None:
        ref_suffix = Path(ref_audio.filename or "ref.wav").suffix or ".wav"
        ref_path = d / f"ref{ref_suffix}"
        with ref_path.open("wb") as f:
            shutil.copyfileobj(ref_audio.file, f)
        try:
            raw = d / "speech_cloned.wav"
            _synth_cloned(text, language, ref_path, raw)
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error",
                            "-i", str(raw), "-ar", "16000", "-ac", "1", str(wav)],
                           check=True, capture_output=True, timeout=120)
            cloned = True
        except Exception as e:  # noqa: BLE001 — cloning must never kill a render
            print(f"[render {job}] cloning failed, falling back to edge-tts: {e}",
                  flush=True)

    if not cloned:
        mp3 = d / "speech.mp3"
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
