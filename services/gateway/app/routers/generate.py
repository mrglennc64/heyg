"""POST /api/v1/generate-avatar-video — the core endpoint."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forge_shared.config import settings
from forge_shared.storage import presigned_url

from ..db import get_session
from ..models import Avatar, Job, Voice
from ..orchestrator import dispatch
from ..schemas import JobAccepted, JobStatus, VideoRequest

router = APIRouter(prefix="/api/v1", tags=["generation"])


async def require_api_key(x_api_key: str = Header(...)) -> None:
    if x_api_key != settings().forge_api_key:
        raise HTTPException(status_code=401, detail="invalid API key")


@router.post(
    "/generate-avatar-video",
    response_model=JobAccepted,
    status_code=202,
    dependencies=[Depends(require_api_key)],
)
async def generate_avatar_video(
    req: VideoRequest,
    session: AsyncSession = Depends(get_session),
) -> JobAccepted:
    # ── validate referenced assets exist before burning GPU time ──
    voice_ids = {s.voice.voice_id for s in req.scenes}
    avatar_ids = {s.avatar.avatar_id for s in req.scenes}

    found_voices = set(
        (await session.execute(select(Voice.id).where(Voice.id.in_(voice_ids)))).scalars()
    )
    if missing := voice_ids - found_voices:
        raise HTTPException(422, f"unknown voice_id(s): {sorted(missing)}")

    found_avatars = set(
        (await session.execute(select(Avatar.id).where(Avatar.id.in_(avatar_ids)))).scalars()
    )
    if missing := avatar_ids - found_avatars:
        raise HTTPException(422, f"unknown avatar_id(s): {sorted(missing)}")

    total_chars = sum(len(s.voice.input_text) for s in req.scenes)
    if total_chars > settings().max_script_chars:
        raise HTTPException(422, f"script exceeds {settings().max_script_chars} chars")

    # ── persist + dispatch ──
    job_id = uuid4().hex[:16]
    job = Job(id=job_id, status="queued", request=req.model_dump())
    session.add(job)
    await session.commit()

    job.canvas_id = dispatch(job_id, req)
    job.status = "synthesizing"
    await session.commit()

    return JobAccepted(job_id=job_id, status_url=f"/api/v1/jobs/{job_id}")


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatus,
    dependencies=[Depends(require_api_key)],
)
async def job_status(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> JobStatus:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")

    progress = {
        "queued": 0.0, "synthesizing": 0.2, "rendering": 0.5,
        "compositing": 0.85, "completed": 1.0, "failed": 0.0,
    }[job.status]

    return JobStatus(
        job_id=job.id,
        status=job.status,
        progress=progress,
        video_url=presigned_url(job.video_key) if job.video_key else None,
        duration_sec=job.duration_sec,
        error=job.error,
    )
