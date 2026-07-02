"""Voice-clone registration with a hard consent gate."""
from __future__ import annotations

import hashlib
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from forge_shared.storage import upload_bytes

from ..db import get_session
from ..models import Voice
from .generate import require_api_key

router = APIRouter(prefix="/api/v1/voices", tags=["voices"],
                   dependencies=[Depends(require_api_key)])

MIN_BYTES = 30 * 48_000 * 2       # ≈ 30 s of 48 kHz 16-bit mono
MAX_BYTES = 200 * 1024 * 1024


@router.get("")
async def list_voices(session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    rows = (await session.execute(select(Voice).order_by(Voice.created_at.desc()))).scalars()
    return [{"voice_id": v.id, "name": v.name} for v in rows]


@router.post("", status_code=201)
async def register_voice(
    name: str = Form(...),
    sample: UploadFile = File(..., description="30 s – 3 min clean speech, wav/flac"),
    consent: UploadFile = File(..., description="Recording of the speaker reading the consent phrase"),
    session: AsyncSession = Depends(get_session),
):
    sample_bytes = await sample.read()
    consent_bytes = await consent.read()

    if not consent_bytes:
        raise HTTPException(403, "voice cloning requires a recorded consent clip")
    if not (MIN_BYTES <= len(sample_bytes) <= MAX_BYTES):
        raise HTTPException(422, "sample must be roughly 30 seconds to 3 minutes")

    voice_id = uuid4().hex[:12]
    sample_key = upload_bytes(sample_bytes, f"voices/{voice_id}/reference.wav")
    upload_bytes(consent_bytes, f"voices/{voice_id}/consent.wav")

    session.add(Voice(
        id=voice_id,
        name=name,
        sample_key=sample_key,
        consent_hash=hashlib.sha256(consent_bytes).hexdigest(),
    ))
    await session.commit()

    # Speaker latents are computed lazily and cached by the voice worker on
    # first synthesis (see services/voice/worker/xtts_engine.py).
    return {"voice_id": voice_id, "name": name}
