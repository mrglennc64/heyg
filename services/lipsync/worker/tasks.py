"""Celery task: lipsync.dub — DriveResult in, LipsyncResult out."""
from __future__ import annotations

from pathlib import Path

from forge_shared.contracts import LipsyncResult
from forge_shared.queue import make_celery
from forge_shared.storage import download, upload

from .musetalk_engine import refine, run_musetalk

app = make_celery("lipsync")


@app.task(name="lipsync.dub", bind=True, max_retries=2)
def dub(self, drive_result: dict, static: dict) -> dict:
    job_id = drive_result["job_id"]
    scene_id = drive_result["scene_id"]

    scratch = Path(f"/scratch/{job_id}/{scene_id}")
    scratch.mkdir(parents=True, exist_ok=True)

    motion = download(drive_result["video_key"], scratch / "motion.mp4")
    audio = download(drive_result["audio_key"], scratch / "speech.wav")

    raw = run_musetalk(motion, audio, scratch)
    final = refine(
        original_video=motion,
        generated_video=raw,
        audio=audio,
        out_path=scratch / "scene.mp4",
        dilate_px=static.get("mask_dilate_px", 12),
        feather_px=static.get("mask_feather_px", 21),
        color_transfer=static.get("color_transfer", True),
    )

    video_key = upload(final, f"jobs/{job_id}/{scene_id}/scene.mp4")
    return LipsyncResult(job_id=job_id, scene_id=scene_id, video_key=video_key).model_dump()
