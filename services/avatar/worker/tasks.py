"""Celery task: avatar.drive — TTSResult (+static avatar config) in, DriveResult out."""
from __future__ import annotations

from pathlib import Path

from forge_shared.contracts import DriveResult, TTSResult
from forge_shared.queue import make_celery
from forge_shared.storage import download, upload

from . import motion_engine

app = make_celery("avatar")


@app.task(name="avatar.drive", bind=True, max_retries=2)
def drive(self, tts_result: dict, static: dict) -> dict:
    tts = TTSResult(**tts_result)
    avatar_id: str = static["avatar_id"]
    mode: str = static.get("mode", "base_video")
    fps: int = static.get("fps", 25)

    scratch = Path(f"/scratch/{tts.job_id}/{tts.scene_id}")
    scratch.mkdir(parents=True, exist_ok=True)
    out_path = scratch / "motion.mp4"
    audio_path = download(tts.audio_key, scratch / "speech.wav")

    if mode == "base_video":
        source = download(f"avatars/{avatar_id}/source.mp4", scratch / "base.mp4")
        motion_engine.drive_base_video(source, out_path, tts.duration_sec, fps)
    else:
        source = download(f"avatars/{avatar_id}/source.png", scratch / "portrait.png")
        motion_engine.drive_still_portrait(source, audio_path, out_path, fps)

    video_key = upload(out_path, f"jobs/{tts.job_id}/{tts.scene_id}/motion.mp4")
    result = DriveResult(
        job_id=tts.job_id, scene_id=tts.scene_id, video_key=video_key, fps=fps
    ).model_dump()
    # thread the audio key through for the lipsync stage
    result["audio_key"] = tts.audio_key
    return result
