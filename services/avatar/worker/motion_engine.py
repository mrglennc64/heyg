"""Motion track generation.

Two paths, selected by avatar kind:

- base_video   → stabilizer ping-pong loop of the user's 15 s clip. Body,
                 hair, clothing, and lighting stay 100% real footage; only
                 the mouth region will be touched downstream by MuseTalk.
                 This is the highest-realism path and the HeyGen default.

- still_portrait → SadTalker generates audio-driven head pose + blink from a
                 single image. LivePortrait can then retarget the result onto
                 the portrait at higher fidelity (optional refinement pass).

Both external repos are vendored under /models and invoked via their CLIs to
keep their (heavy, conflicting) dependency trees out of this image.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .stabilizer import build_pingpong_track

SADTALKER_DIR = Path(os.environ.get("SADTALKER_DIR", "/models/sadtalker"))
LIVEPORTRAIT_DIR = Path(os.environ.get("LIVEPORTRAIT_DIR", "/models/liveportrait"))


def drive_base_video(
    base_video: Path, out_path: Path, duration: float, fps: int
) -> Path:
    return build_pingpong_track(base_video, out_path, duration, fps)


def drive_still_portrait(
    portrait: Path, audio: Path, out_path: Path, fps: int,
    enhance: bool = True,
) -> Path:
    """SadTalker: audio → head-pose/blink/expression coefficients → video."""
    result_dir = out_path.parent / "sadtalker_out"
    cmd = [
        "python", str(SADTALKER_DIR / "inference.py"),
        "--driven_audio", str(audio),
        "--source_image", str(portrait),
        "--result_dir", str(result_dir),
        "--still",                      # damp body motion — reduces warping
        "--preprocess", "full",         # keep full frame, not just crop
        "--pose_style", "0",
        "--expression_scale", "1.0",
        "--fps", str(fps),
    ]
    if enhance:
        cmd += ["--enhancer", "gfpgan"]  # face restoration pass
    subprocess.run(cmd, check=True, cwd=SADTALKER_DIR)

    produced = sorted(result_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if not produced:
        raise RuntimeError("SadTalker produced no output")
    produced[-1].replace(out_path)
    return out_path
