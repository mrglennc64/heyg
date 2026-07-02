"""Inter-service payload contracts.

These are the *wire* schemas passed between Celery stages — deliberately flat
and JSON-serializable. The gateway's public schema (services/gateway/app/
schemas.py) is richer and normalizes down to these.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class TTSRequest(BaseModel):
    job_id: str
    scene_id: str
    voice_id: str                       # registered clone (speaker-latent key)
    text: str
    language: str = "en"                # ISO 639-1; XTTS v2 supports 17
    speed: float = Field(1.0, ge=0.5, le=2.0)
    pitch_semitones: float = Field(0.0, ge=-6.0, le=6.0)
    emotion: Literal["neutral", "friendly", "serious", "excited", "sad"] = "neutral"
    temperature: float = Field(0.65, ge=0.1, le=1.2)  # XTTS sampling temp


class TTSResult(BaseModel):
    job_id: str
    scene_id: str
    audio_key: str                      # s3 key: 48 kHz mono wav
    duration_sec: float
    word_timestamps_key: Optional[str] = None   # whisper alignment JSON


class DriveRequest(BaseModel):
    job_id: str
    scene_id: str
    avatar_id: str
    audio_key: str
    duration_sec: float
    mode: Literal["base_video", "still_portrait"] = "base_video"
    fps: int = 25


class DriveResult(BaseModel):
    job_id: str
    scene_id: str
    video_key: str                      # motion track, correct length, no lipsync yet
    fps: int


class LipsyncRequest(BaseModel):
    job_id: str
    scene_id: str
    video_key: str
    audio_key: str
    mask_feather_px: int = 21           # gaussian feather radius on alpha edge
    mask_dilate_px: int = 12            # expansion beyond jaw landmarks
    color_transfer: bool = True         # LAB-match inpainted region to original


class LipsyncResult(BaseModel):
    job_id: str
    scene_id: str
    video_key: str                      # lipsynced avatar clip w/ audio muxed


class CompositeRequest(BaseModel):
    job_id: str
    scene_graph: dict                   # full normalized VideoRequest dump
    scene_clips: list[LipsyncResult]


class CompositeResult(BaseModel):
    job_id: str
    video_key: str
    duration_sec: float
    width: int
    height: int
