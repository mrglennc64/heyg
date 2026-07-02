"""MuseTalk inference wrapper + masked recomposition.

MuseTalk runs zero-shot (no per-avatar training), inpaints the lower half of
the face conditioned on Whisper audio features, and holds ~30 fps on an A100
class GPU — which makes it the right engine for the dubbing/lip-sync stage.
Language-agnostic by construction: it consumes audio features, not text, so
the same avatar dubs into any language XTTS can speak.

We deliberately DON'T ship MuseTalk's raw output: its full-crop paste-back is
where seams come from. Instead we run its generator, then recomposite every
frame through masking.composite() (landmark alpha + LAB transfer).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import cv2

from .masking import composite

MUSETALK_DIR = Path(os.environ.get("MUSETALK_DIR", "/models/musetalk"))


def run_musetalk(video: Path, audio: Path, work_dir: Path) -> Path:
    """Invoke vendored MuseTalk CLI → raw lipsynced mp4 (unrefined paste-back)."""
    out_dir = work_dir / "musetalk_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "python", "-m", "scripts.inference",
            "--inference_config", "none",
            "--video_path", str(video),
            "--audio_path", str(audio),
            "--result_dir", str(out_dir),
            "--fps", "25",
            "--batch_size", "8",
        ],
        check=True, cwd=MUSETALK_DIR,
    )
    produced = sorted(out_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if not produced:
        raise RuntimeError("MuseTalk produced no output")
    return produced[-1]


def refine(
    original_video: Path,
    generated_video: Path,
    audio: Path,
    out_path: Path,
    dilate_px: int = 12,
    feather_px: int = 21,
    color_transfer: bool = True,
) -> Path:
    """Frame-parallel masked recomposition, then mux the speech track."""
    cap_o = cv2.VideoCapture(str(original_video))
    cap_g = cv2.VideoCapture(str(generated_video))
    fps = cap_o.get(cv2.CAP_PROP_FPS) or 25
    w = int(cap_o.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap_o.get(cv2.CAP_PROP_FRAME_HEIGHT))

    silent = out_path.with_suffix(".silent.mp4")
    writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    while True:
        ok_o, frame_o = cap_o.read()
        ok_g, frame_g = cap_g.read()
        if not (ok_o and ok_g):
            break
        if frame_g.shape[:2] != frame_o.shape[:2]:
            frame_g = cv2.resize(frame_g, (w, h))
        writer.write(composite(frame_o, frame_g, dilate_px, feather_px, color_transfer))

    for c in (cap_o, cap_g, writer):
        c.release()

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(silent), "-i", str(audio),
         "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-shortest", str(out_path)],
        check=True, capture_output=True,
    )
    silent.unlink(missing_ok=True)
    return out_path
