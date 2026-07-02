"""Public API schema — HeyGen-compatible-ish scene graph.

A request is a list of scenes; each scene binds one avatar + one voice track
to a background and optional overlays. Mirrors HeyGen's `video_inputs` shape
closely enough that existing HeyGen client payloads port with minor renames.
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class Dimension(BaseModel):
    width: int = Field(1920, ge=256, le=3840)
    height: int = Field(1080, ge=256, le=2160)

    @field_validator("width", "height")
    @classmethod
    def _even(cls, v: int) -> int:
        if v % 2:
            raise ValueError("dimensions must be even (yuv420p)")
        return v


class Position(BaseModel):
    """Normalized canvas coordinates — (0.5, 0.5) is centered."""
    x: float = Field(0.5, ge=0.0, le=1.0)
    y: float = Field(0.5, ge=0.0, le=1.0)


class AvatarLayer(BaseModel):
    avatar_id: str                      # registered via POST /api/v1/avatars
    mode: Literal["base_video", "still_portrait"] = "base_video"
    scale: float = Field(1.0, ge=0.1, le=2.0)
    position: Position = Position()
    matting: Literal["none", "greenscreen", "alpha"] = "none"


class VoiceTrack(BaseModel):
    voice_id: str                       # registered via POST /api/v1/voices
    input_text: str = Field(..., min_length=1, max_length=20_000)
    language: str = "en"                # target language — dubbing happens here
    speed: float = Field(1.0, ge=0.5, le=2.0)
    pitch_semitones: float = Field(0.0, ge=-6.0, le=6.0)
    emotion: Literal["neutral", "friendly", "serious", "excited", "sad"] = "neutral"


class Background(BaseModel):
    type: Literal["color", "image", "video"] = "color"
    value: str = "#0b0f19"              # hex color, or s3 key / URL for media
    fit: Literal["cover", "contain"] = "cover"


class Overlay(BaseModel):
    type: Literal["text", "image"] = "text"
    value: str
    position: Position = Position()
    scale: float = 1.0
    start_sec: float = 0.0
    end_sec: Optional[float] = None     # None → until scene end
    font_size: int = 48
    font_color: str = "#ffffff"


class Scene(BaseModel):
    scene_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    avatar: AvatarLayer
    voice: VoiceTrack
    background: Background = Background()
    overlays: list[Overlay] = []
    transition: Literal["cut", "fade", "wipeleft", "slideright"] = "cut"
    captions: bool = False              # burn word-level captions from alignment


class VideoRequest(BaseModel):
    title: str = "untitled"
    dimension: Dimension = Dimension()
    fps: Literal[24, 25, 30, 50, 60] = 25
    scenes: list[Scene] = Field(..., min_length=1, max_length=50)
    callback_url: Optional[str] = None  # webhook on completion
    test_mode: bool = False             # 540p fast path, visible watermark


class JobAccepted(BaseModel):
    job_id: str
    status: Literal["queued"] = "queued"
    status_url: str


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "synthesizing", "rendering", "compositing",
                    "completed", "failed"]
    progress: float = 0.0               # 0..1, coarse per-stage
    video_url: Optional[str] = None     # presigned MP4 URL when completed
    duration_sec: Optional[float] = None
    error: Optional[str] = None
