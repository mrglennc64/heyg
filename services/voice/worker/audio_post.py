"""Post-processing: chunk crossfade, pitch/speed, resample, EBU R128 loudnorm."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

XTTS_SR = 24_000
TARGET_SR = 48_000
CROSSFADE_MS = 40


def stitch(waves: list[np.ndarray], sr: int = XTTS_SR) -> np.ndarray:
    """Equal-power crossfade between synthesized chunks — kills boundary clicks."""
    fade = int(sr * CROSSFADE_MS / 1000)
    out = waves[0]
    for w in waves[1:]:
        if len(out) < fade or len(w) < fade:
            out = np.concatenate([out, w])
            continue
        t = np.linspace(0, np.pi / 2, fade)
        tail = out[-fade:] * np.cos(t) ** 2 + w[:fade] * np.sin(t) ** 2
        out = np.concatenate([out[:-fade], tail, w[fade:]])
    return out


def finalize(
    wave: np.ndarray,
    out_path: str | Path,
    speed: float = 1.0,
    pitch_semitones: float = 0.0,
) -> float:
    """Apply prosody + loudness, write 48 kHz mono wav. Returns duration (s)."""
    raw = Path(out_path).with_suffix(".raw.wav")
    sf.write(raw, wave.astype(np.float32), XTTS_SR)

    # rubberband keeps formants intact → no chipmunk artifacts on pitch shift
    filters = [f"aresample={TARGET_SR}"]
    if pitch_semitones:
        filters.append(f"rubberband=pitch={2 ** (pitch_semitones / 12):.6f}")
    if speed != 1.0:
        filters.append(f"atempo={max(0.5, min(2.0, speed)):.4f}")
    filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")   # EBU R128 broadcast target

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw), "-af", ",".join(filters),
         "-ac", "1", "-c:a", "pcm_s16le", str(out_path)],
        check=True, capture_output=True,
    )
    raw.unlink(missing_ok=True)

    info = sf.info(str(out_path))
    return info.frames / info.samplerate
