"""Long-form stability: turn a 15 s base clip into an N-second seamless track.

Naive looping produces a visible "jump" every 15 s — the #1 uncanny-valley
trigger in long-form avatar video. Two defenses:

1. PING-PONG LOOP: play forward, then reversed, alternating. Every frame
   boundary is continuous by construction (frame N → frame N), so there is
   never a temporal seam. Reversed segments read as natural idle sway.
2. MICRO-TRIM to a motion-minimum: we trim the base clip to end on the frame
   most similar to its first frame (L2 over downsampled grayscale), which
   halves the perceived direction-reversal at ping-pong turnarounds.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np


def _frame_signatures(video: Path, size: int = 64) -> np.ndarray:
    cap = cv2.VideoCapture(str(video))
    sigs = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sigs.append(cv2.resize(g, (size, size)).astype(np.float32).ravel())
    cap.release()
    return np.stack(sigs)


def best_loop_end(video: Path, min_keep_ratio: float = 0.6) -> int:
    """Frame index (exclusive) where the clip most resembles its start."""
    sigs = _frame_signatures(video)
    n = len(sigs)
    lo = int(n * min_keep_ratio)
    dists = np.linalg.norm(sigs[lo:] - sigs[0], axis=1)
    return lo + int(np.argmin(dists)) + 1


def build_pingpong_track(
    base_video: Path,
    out_path: Path,
    target_duration: float,
    fps: int = 25,
) -> Path:
    """Concat forward/reversed segments until >= target_duration, then trim."""
    end_frame = best_loop_end(base_video)
    seg_seconds = end_frame / fps

    work = out_path.parent
    fwd = work / "seg_fwd.mp4"
    rev = work / "seg_rev.mp4"

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(base_video),
         "-frames:v", str(end_frame), "-an",
         "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(fwd)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(fwd), "-vf", "reverse", "-an",
         "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(rev)],
        check=True, capture_output=True,
    )

    reps = int(np.ceil(target_duration / seg_seconds)) + 1
    concat_list = work / "concat.txt"
    lines = [f"file '{(fwd if i % 2 == 0 else rev).name}'" for i in range(reps)]
    concat_list.write_text("\n".join(lines))

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-t", f"{target_duration:.3f}",
         "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
         "-r", str(fps), str(out_path)],
        check=True, capture_output=True, cwd=work,
    )
    return out_path
