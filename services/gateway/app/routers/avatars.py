"""Avatar registration — a 15 s base video or a still portrait."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from forge_shared.storage import upload_bytes

from ..db import get_session
from ..models import Avatar
from .generate import require_api_key

router = APIRouter(prefix="/api/v1/avatars", tags=["avatars"],
                   dependencies=[Depends(require_api_key)])

KIND_EXT = {"base_video": "mp4", "still_portrait": "png"}


@router.post("", status_code=201)
async def register_avatar(
    name: str = Form(...),
    kind: str = Form("base_video"),
    media: UploadFile = File(..., description="≈15 s neutral-motion mp4, or a portrait png"),
    session: AsyncSession = Depends(get_session),
):
    if kind not in KIND_EXT:
        raise HTTPException(422, f"kind must be one of {list(KIND_EXT)}")

    data = await media.read()
    if not data:
        raise HTTPException(422, "empty upload")

    avatar_id = uuid4().hex[:12]
    media_key = upload_bytes(data, f"avatars/{avatar_id}/source.{KIND_EXT[kind]}")

    session.add(Avatar(id=avatar_id, name=name, kind=kind, media_key=media_key))
    await session.commit()
    return {"avatar_id": avatar_id, "name": name, "kind": kind}
