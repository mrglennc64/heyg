"""Celery task: voice.synthesize — TTSRequest in, TTSResult out."""
from __future__ import annotations

from pathlib import Path

from forge_shared.contracts import TTSRequest, TTSResult
from forge_shared.queue import make_celery
from forge_shared.storage import upload

from .audio_post import finalize, stitch
from .xtts_engine import XTTSEngine

app = make_celery("voice")


@app.task(name="voice.synthesize", bind=True, max_retries=2)
def synthesize(self, payload: dict) -> dict:
    req = TTSRequest(**payload)
    engine = XTTSEngine.get()

    # reference sample lives at a deterministic key set by the gateway
    reference_key = f"voices/{req.voice_id}/reference.wav"

    waves = engine.synthesize(
        text=req.text,
        voice_id=req.voice_id,
        reference_key=reference_key,
        language=req.language,
        emotion=req.emotion,
        temperature=req.temperature,
    )

    out_dir = Path(f"/scratch/{req.job_id}/{req.scene_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / "speech.wav"

    duration = finalize(
        stitch([w.numpy() for w in waves]),
        wav_path,
        speed=req.speed,
        pitch_semitones=req.pitch_semitones,
    )

    audio_key = upload(wav_path, f"jobs/{req.job_id}/{req.scene_id}/speech.wav")
    return TTSResult(
        job_id=req.job_id,
        scene_id=req.scene_id,
        audio_key=audio_key,
        duration_sec=duration,
    ).model_dump()
