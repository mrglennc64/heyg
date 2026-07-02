"""Compiles a validated VideoRequest into a Celery canvas.

Per scene:   voice.synthesize → avatar.drive → lipsync.dub      (chain)
Whole job:   chord(all scene chains) → compositor.render        (fan-in)

Workers are addressed by task *name* only — the gateway never imports GPU
code. Stage payloads are the pydantic contracts in forge_shared.contracts,
serialized to dicts.
"""
from __future__ import annotations

from celery import chain, chord

from forge_shared.queue import make_celery

from .schemas import VideoRequest

celery_app = make_celery("gateway")

# Signatures by name; queue selection comes from forge_shared.queue.TASK_ROUTES.
_tts = celery_app.signature("voice.synthesize")
_drive = celery_app.signature("avatar.drive")
_dub = celery_app.signature("lipsync.dub")
_render = celery_app.signature("compositor.render")


def dispatch(job_id: str, req: VideoRequest) -> str:
    """Fan out scene pipelines, fan in to the compositor. Returns canvas id."""
    scene_chains = []
    for scene in req.scenes:
        tts_payload = {
            "job_id": job_id,
            "scene_id": scene.scene_id,
            "voice_id": scene.voice.voice_id,
            "text": scene.voice.input_text,
            "language": scene.voice.language,
            "speed": scene.voice.speed,
            "pitch_semitones": scene.voice.pitch_semitones,
            "emotion": scene.voice.emotion,
        }
        drive_payload = {
            "avatar_id": scene.avatar.avatar_id,
            "mode": scene.avatar.mode,
            "fps": req.fps,
        }
        # Each stage receives the previous stage's result dict as first arg
        # and merges its own static kwargs.
        scene_chains.append(
            chain(
                _tts.clone(kwargs={"payload": tts_payload}),
                _drive.clone(kwargs={"static": drive_payload}),
                _dub.clone(kwargs={"static": {}}),
            )
        )

    canvas = chord(scene_chains)(
        _render.clone(kwargs={
            "job_id": job_id,
            "scene_graph": req.model_dump(),
        })
    )
    return canvas.id
