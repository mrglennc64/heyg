from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    request: Mapped[dict] = mapped_column(JSON)
    canvas_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    video_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Voice(Base):
    __tablename__ = "voices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    sample_key: Mapped[str] = mapped_column(String(512))      # 30s–3min reference wav
    latents_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    consent_hash: Mapped[str] = mapped_column(String(64))     # sha256 of consent clip
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Avatar(Base):
    __tablename__ = "avatars"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16))             # base_video | still_portrait
    media_key: Mapped[str] = mapped_column(String(512))       # 15s mp4 or portrait png
    face_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # bbox, landmarks
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
