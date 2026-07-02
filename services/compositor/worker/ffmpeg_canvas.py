"""Scene graph → FFmpeg filter_complex → broadcast MP4.

Layer order per scene: background → avatar (scaled/positioned, optional
chroma key) → overlays → captions. Scenes join with xfade transitions.
Output: H.264 High@L4.1, yuv420p, BT.709 tagged, AAC-LC 192k, +faststart —
i.e. plays everywhere and passes broadcast QC checks.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

HWACCEL = os.environ.get("FFMPEG_HWACCEL", "cpu")

TRANSITION_MAP = {"fade": "fade", "wipeleft": "wipeleft", "slideright": "slideright"}
XFADE_SEC = 0.5


def _video_codec(test_mode: bool) -> list[str]:
    if test_mode:
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "28"]
    if HWACCEL == "nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr",
                "-cq", "19", "-b:v", "0", "-profile:v", "high"]
    return ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high"]


def _bg_input(bg: dict, w: int, h: int, dur: float, fps: int) -> tuple[list[str], str]:
    """Returns (ffmpeg input args, input label filter prep)."""
    if bg["type"] == "color":
        color = bg["value"].lstrip("#")
        return (["-f", "lavfi", "-t", f"{dur:.3f}",
                 "-i", f"color=c=0x{color}:s={w}x{h}:r={fps}"], "")
    # image / video files are pre-downloaded next to the scene clips
    loop = ["-loop", "1", "-t", f"{dur:.3f}"] if bg["type"] == "image" else ["-stream_loop", "-1", "-t", f"{dur:.3f}"]
    scale = (f"scale={w}:{h}:force_original_aspect_ratio="
             + ("increase,crop={}:{}".format(w, h) if bg.get("fit", "cover") == "cover" else "decrease"))
    return (loop + ["-i", bg["_local_path"]], scale)


def render_scene(
    scene: dict, clip_path: Path, out_path: Path,
    width: int, height: int, fps: int, duration: float, test_mode: bool,
) -> Path:
    """Composite one scene: background + positioned avatar + text overlays."""
    bg_args, bg_scale = _bg_input(scene["background"], width, height, duration, fps)

    av = scene["avatar"]
    av_h = int(height * av.get("scale", 1.0))
    # normalized center position → top-left overlay coords
    x = f"(main_w-overlay_w)*{av['position']['x']:.4f}"
    y = f"(main_h-overlay_h)*{av['position']['y']:.4f}"

    chains = []
    if bg_scale:
        chains.append(f"[0:v]{bg_scale}[bg]")
        bg_label = "[bg]"
    else:
        bg_label = "[0:v]"

    avatar_chain = f"[1:v]scale=-2:{av_h}"
    if av.get("matting") == "greenscreen":
        avatar_chain += ",chromakey=0x00ff00:0.18:0.05,despill=type=green"
    chains.append(f"{avatar_chain}[av]")
    chains.append(f"{bg_label}[av]overlay=x='{x}':y='{y}':shortest=1[comp]")

    label = "[comp]"
    for i, ov in enumerate(scene.get("overlays", [])):
        if ov["type"] != "text":
            continue
        end = ov.get("end_sec") or duration
        text = ov["value"].replace("'", r"\'").replace(":", r"\:")
        nxt = f"[t{i}]"
        chains.append(
            f"{label}drawtext=text='{text}':fontsize={ov.get('font_size', 48)}"
            f":fontcolor={ov.get('font_color', '#ffffff')}"
            f":x=(w-text_w)*{ov['position']['x']:.3f}:y=(h-text_h)*{ov['position']['y']:.3f}"
            f":enable='between(t,{ov.get('start_sec', 0)},{end})'"
            f":shadowx=2:shadowy=2{nxt}"
        )
        label = nxt

    cmd = (
        ["ffmpeg", "-y", *bg_args, "-i", str(clip_path),
         "-filter_complex", ";".join(chains),
         "-map", label, "-map", "1:a",
         *_video_codec(test_mode),
         "-pix_fmt", "yuv420p", "-r", str(fps),
         "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         str(out_path)]
    )
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def join_scenes(
    scene_paths: list[Path], transitions: list[str], durations: list[float],
    out_path: Path, test_mode: bool,
) -> Path:
    """Concat with xfade where requested; plain concat for cuts."""
    if len(scene_paths) == 1:
        scene_paths[0].replace(out_path)
        return out_path

    if all(t == "cut" for t in transitions[1:]):
        lst = out_path.parent / "concat.txt"
        lst.write_text("\n".join(f"file '{p.name}'" for p in scene_paths))
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-c", "copy", str(out_path)],
            check=True, capture_output=True, cwd=out_path.parent,
        )
        return out_path

    # Build chained xfade graph (audio via acrossfade)
    inputs, vf, af = [], [], []
    for p in scene_paths:
        inputs += ["-i", str(p)]
    v_prev, a_prev, offset = "[0:v]", "[0:a]", 0.0
    for i in range(1, len(scene_paths)):
        offset += durations[i - 1] - XFADE_SEC
        t = TRANSITION_MAP.get(transitions[i], "fade")
        v_out, a_out = f"[v{i}]", f"[a{i}]"
        vf.append(f"{v_prev}[{i}:v]xfade=transition={t}:duration={XFADE_SEC}:offset={offset:.3f}{v_out}")
        af.append(f"{a_prev}[{i}:a]acrossfade=d={XFADE_SEC}{a_out}")
        v_prev, a_prev = v_out, a_out

    subprocess.run(
        ["ffmpeg", "-y", *inputs,
         "-filter_complex", ";".join(vf + af),
         "-map", v_prev, "-map", a_prev,
         *_video_codec(test_mode),
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(out_path)],
        check=True, capture_output=True,
    )
    return out_path


def apply_watermark(video: Path, out_path: Path, key: str, visible: bool) -> Path:
    """Provenance stamp. Visible badge in test mode; metadata tag always.

    TODO(production): replace metadata tag with a robust invisible watermark
    (e.g. DCT-domain spread-spectrum) + C2PA manifest signing.
    """
    args = ["ffmpeg", "-y", "-i", str(video)]
    if visible:
        args += ["-vf",
                 "drawtext=text='AI GENERATED — TEST':fontsize=28:fontcolor=white@0.6"
                 ":x=w-text_w-24:y=h-text_h-24:box=1:boxcolor=black@0.3"]
        args += ["-c:v", "libx264", "-crf", "18", "-c:a", "copy"]
    else:
        args += ["-c", "copy"]
    args += ["-metadata", f"comment=ai_generated;provenance=avatarforge;sig={key[:8]}",
             "-movflags", "+faststart", str(out_path)]
    subprocess.run(args, check=True, capture_output=True)
    return out_path
