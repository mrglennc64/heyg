"""Celery task: compositor.render — chord fan-in over all scene clips → final MP4.

Also owns job bookkeeping: it is the only worker that writes job status back
to Postgres (sync psycopg — workers stay out of the async gateway stack).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import psycopg
from forge_shared.config import settings
from forge_shared.contracts import CompositeResult
from forge_shared.queue import make_celery
from forge_shared.storage import download, presigned_url, upload

from .ffmpeg_canvas import apply_watermark, join_scenes, render_scene

app = make_celery("compositor")

PG_DSN = "postgresql://forge:{pw}@postgres:5432/forge"


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def _update_job(job_id: str, **fields) -> None:
    import os
    dsn = PG_DSN.format(pw=os.environ.get("POSTGRES_PASSWORD", "forge"))
    sets = ", ".join(f"{k} = %s" for k in fields)
    with psycopg.connect(dsn) as conn:
        conn.execute(f"UPDATE jobs SET {sets}, updated_at = now() WHERE id = %s",
                     (*fields.values(), job_id))


@app.task(name="compositor.render", bind=True)
def render(self, scene_results: list[dict], job_id: str, scene_graph: dict) -> dict:
    try:
        _update_job(job_id, status="compositing")

        dim = scene_graph["dimension"]
        fps = scene_graph["fps"]
        test_mode = scene_graph.get("test_mode", False)
        if test_mode:
            dim = {"width": 960, "height": 540}

        scratch = Path(f"/scratch/{job_id}/composite")
        scratch.mkdir(parents=True, exist_ok=True)

        # chord results arrive unordered → re-order by scene graph
        by_scene = {r["scene_id"]: r for r in scene_results}
        rendered, durations, transitions = [], [], []

        for scene in scene_graph["scenes"]:
            clip_result = by_scene[scene["scene_id"]]
            clip = download(clip_result["video_key"], scratch / f"{scene['scene_id']}.mp4")
            dur = _probe_duration(clip)

            # pre-fetch media backgrounds
            bg = scene["background"]
            if bg["type"] in ("image", "video") and not bg["value"].startswith("#"):
                bg["_local_path"] = str(download(bg["value"], scratch / f"bg_{scene['scene_id']}"))

            out = render_scene(
                scene, clip, scratch / f"scene_{scene['scene_id']}.mp4",
                dim["width"], dim["height"], fps, dur, test_mode,
            )
            rendered.append(out)
            durations.append(dur)
            transitions.append(scene.get("transition", "cut"))

        joined = join_scenes(rendered, transitions, durations,
                             scratch / "joined.mp4", test_mode)

        final = scratch / "final.mp4"
        if settings().watermark_enabled:
            apply_watermark(joined, final, settings().watermark_key, visible=test_mode)
        else:
            joined.replace(final)

        total = _probe_duration(final)
        video_key = upload(final, f"jobs/{job_id}/final.mp4")

        _update_job(job_id, status="completed", video_key=video_key, duration_sec=total)
        _maybe_callback(scene_graph, job_id, video_key, total)

        return CompositeResult(
            job_id=job_id, video_key=video_key, duration_sec=total,
            width=dim["width"], height=dim["height"],
        ).model_dump()

    except Exception as exc:
        _update_job(job_id, status="failed", error=str(exc)[:2000])
        raise


def _maybe_callback(scene_graph: dict, job_id: str, video_key: str, duration: float) -> None:
    url = scene_graph.get("callback_url")
    if not url:
        return
    import httpx
    try:
        httpx.post(url, json={
            "job_id": job_id,
            "status": "completed",
            "video_url": presigned_url(video_key),
            "duration_sec": duration,
        }, timeout=10)
    except httpx.HTTPError:
        pass  # webhook failures never fail the job
