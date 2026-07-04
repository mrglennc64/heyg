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
MUSETALK_DIR = Path("/workspace/MuseTalk")
MUSETALK_PY = Path("/workspace/venvs/mt/bin/python")
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


ENHANCE_STATUS = {"engine": None}


def _probe_enhancer() -> None:
    try:
        from resemble_enhance.enhancer.inference import enhance  # noqa: F401
        ENHANCE_STATUS["engine"] = "resemble-enhance"
    except Exception as e:  # noqa: BLE001
        ENHANCE_STATUS["engine"] = f"unavailable: {type(e).__name__}: {e}"[:200]


threading.Thread(target=_probe_clone_engine, daemon=True).start()
threading.Thread(target=_probe_enhancer, daemon=True).start()


def _enhance_audio(raw: Path, d: Path) -> Path:
    """24 kHz cloned speech → 44.1 kHz via resemble-enhance; raw on any failure."""
    if ENHANCE_STATUS["engine"] != "resemble-enhance":
        return raw
    try:
        import torch
        import torchaudio
        from resemble_enhance.enhancer.inference import enhance

        dwav, sr = torchaudio.load(str(raw))
        dwav = dwav.mean(0)
        wav, nsr = enhance(dwav, sr, "cuda", nfe=32, solver="midpoint",
                           lambd=0.9, tau=0.5)
        enh = d / "enhanced.wav"
        torchaudio.save(str(enh), wav.unsqueeze(0).cpu(), nsr)
        return enh
    except Exception as e:  # noqa: BLE001 — enhancement is best-effort
        print(f"[tts] enhance failed, using raw synth: {e}", flush=True)
        return raw

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
    engines = ["wav2lip"]
    if MUSETALK_PY.exists() and (MUSETALK_DIR / "models/musetalkV15/unet.pth").exists():
        engines.append("musetalk")
    return {
        "ok": True,
        "cuda": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "clone_engine": CLONE_STATUS["engine"],
        "enhance_engine": ENHANCE_STATUS["engine"],
        "engines": engines,
    }


def _run_wav2lip(face_path: Path, wav: Path, out: Path) -> None:
    subprocess.run(
        ["python", "inference.py",
         "--checkpoint_path", "checkpoints/wav2lip_gan.pth",
         "--face", str(face_path), "--audio", str(wav),
         "--outfile", str(out), "--pads", "0", "15", "0", "0", "--nosmooth"],
        check=True, capture_output=True, cwd=WAV2LIP, timeout=900,
    )


def _run_musetalk(face_path: Path, wav: Path, d: Path, out: Path) -> None:
    """MuseTalk 1.5 via its own venv (torch pins differ from the service env)."""
    cfg = d / "mt.yaml"
    cfg.write_text(f"task_0:\n  video_path: {face_path}\n  audio_path: {wav}\n")
    result_dir = d / "mt_out"
    subprocess.run(
        [str(MUSETALK_PY), "-m", "scripts.inference",
         "--inference_config", str(cfg),
         "--result_dir", str(result_dir),
         "--unet_model_path", "models/musetalkV15/unet.pth",
         "--unet_config", "models/musetalkV15/musetalk.json",
         "--version", "v15"],
        check=True, capture_output=True, cwd=MUSETALK_DIR, timeout=1800,
    )
    produced = sorted(result_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if not produced:
        raise RuntimeError("musetalk produced no mp4")
    produced[-1].replace(out)


@app.post("/tts")
async def tts(
    text: str = Form(...),
    language: str = Form("en"),
    fmt: str = Form("mp3"),
    ref_audio: UploadFile = File(...),
):
    """Audio-only cloned speech at audiobook quality.

    chatterbox 24 kHz → resemble-enhance 44.1 kHz (when installed) →
    loudnorm to ACX levels (RMS −18..−23 dB, −3 dB peaks) → 44.1 kHz
    mono wav, or 192 kbps CBR mp3 (the ACX upload format).
    """
    if fmt not in ("mp3", "wav"):
        raise HTTPException(422, "fmt must be mp3 or wav")
    job = uuid.uuid4().hex[:12]
    d = WORK / job
    d.mkdir(parents=True, exist_ok=True)

    ref_suffix = Path(ref_audio.filename or "ref.wav").suffix or ".wav"
    ref_path = d / f"ref{ref_suffix}"
    with ref_path.open("wb") as f:
        shutil.copyfileobj(ref_audio.file, f)

    raw = d / "speech.wav"
    try:
        _synth_cloned(text, language, ref_path, raw)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"cloning failed: {e}")

    src = _enhance_audio(raw, d)

    final = d / f"audiobook.{fmt}"
    codec = ["-c:a", "libmp3lame", "-b:a", "192k"] if fmt == "mp3" else []
    try:
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error",
                        "-i", str(src),
                        "-af", "loudnorm=I=-19:TP=-3:LRA=11",
                        "-ar", "44100", "-ac", "1", *codec, str(final)],
                       check=True, capture_output=True, timeout=600)
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"mastering failed: {e.stderr.decode()[:400]}")
    media = "audio/mpeg" if fmt == "mp3" else "audio/wav"
    return FileResponse(final, media_type=media, filename=f"audiobook_{job}.{fmt}")


@app.post("/render")
async def render(
    face: UploadFile = File(...),
    text: str = Form(...),
    voice: str = Form("en-US-JennyNeural"),
    language: str = Form("en"),
    engine: str = Form("wav2lip"),
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

    # 2. speech — cloned when a reference sample came along, else edge-tts.
    # The 16 kHz mono wav exists only for the lip-sync models' features; hq
    # keeps the native-rate audio for the final mux.
    wav = d / "speech.wav"
    hq: Path | None = None
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
            hq = raw
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
            hq = mp3
        except subprocess.CalledProcessError as e:
            raise HTTPException(500, f"tts failed: {e.stderr.decode()[:500]}")

    # 3. lip-sync on GPU — engine-selectable (wav2lip | musetalk)
    if engine == "musetalk" and not (MUSETALK_PY.exists()
                                     and (MUSETALK_DIR / "models/musetalkV15/unet.pth").exists()):
        print(f"[render {job}] musetalk requested but not installed — wav2lip fallback", flush=True)
        engine = "wav2lip"
    out = d / "avatar.mp4"
    try:
        if engine == "musetalk":
            _run_musetalk(face_path, wav, d, out)
        else:
            _run_wav2lip(face_path, wav, out)
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"render failed ({engine}): {e.stderr.decode()[-800:]}")
    except RuntimeError as e:
        raise HTTPException(500, f"render failed ({engine}): {e}")

    if not out.exists():
        raise HTTPException(500, "no output produced")

    # 4. remux the native-rate audio over the model's 16 kHz track
    if hq is not None:
        final = d / "avatar_hq.mp4"
        try:
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error",
                            "-i", str(out), "-i", str(hq),
                            "-map", "0:v", "-map", "1:a",
                            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                            "-shortest", str(final)],
                           check=True, capture_output=True, timeout=180)
            out = final
        except subprocess.CalledProcessError as e:
            print(f"[render {job}] hq remux failed, serving 16k audio: "
                  f"{e.stderr.decode()[:300]}", flush=True)
    return FileResponse(out, media_type="video/mp4", filename=f"avatar_{job}.mp4")
