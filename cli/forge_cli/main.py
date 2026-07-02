"""forge — CLI for AvatarForge.

Command surface mirrors HeyGen's three agent skills:
  forge avatar create        (heygen-avatar: digital twin registration)
  forge voice  create        (heygen-avatar: voice half of the twin)
  forge video  generate      (heygen-video:  script → mp4)
  forge video  translate     (heygen-translate: same graph, new language)
  forge job    status|wait|download
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import httpx

from . import client as api
from .client import EXIT_USAGE, die, emit, info, request, wait_for_job


@click.group()
@click.version_option(package_name="forge-cli")
def cli() -> None:
    """AvatarForge CLI — JSON on stdout, progress on stderr, stable exit codes."""


# ────────────────────────── avatar ──────────────────────────
@cli.group()
def avatar() -> None:
    """Register and inspect avatars (digital twins)."""


@avatar.command("create")
@click.option("--name", required=True)
@click.option("--media", required=True, type=click.Path(exists=True, path_type=Path),
              help="≈15 s neutral-motion mp4, or a portrait png")
@click.option("--kind", type=click.Choice(["base_video", "still_portrait"]),
              default="base_video", show_default=True)
def avatar_create(name: str, media: Path, kind: str) -> None:
    with media.open("rb") as f:
        result = request("POST", "/api/v1/avatars",
                         data={"name": name, "kind": kind},
                         files={"media": (media.name, f)})
    emit(result)


# ────────────────────────── voice ──────────────────────────
@cli.group()
def voice() -> None:
    """Register cloned voices (consent clip required)."""


@voice.command("create")
@click.option("--name", required=True)
@click.option("--sample", required=True, type=click.Path(exists=True, path_type=Path),
              help="30 s – 3 min of clean speech (wav/flac)")
@click.option("--consent", required=True, type=click.Path(exists=True, path_type=Path),
              help="Recording of the speaker reading the consent phrase")
def voice_create(name: str, sample: Path, consent: Path) -> None:
    with sample.open("rb") as fs, consent.open("rb") as fc:
        result = request("POST", "/api/v1/voices",
                         data={"name": name},
                         files={"sample": (sample.name, fs),
                                "consent": (consent.name, fc)})
    emit(result)


# ────────────────────────── video ──────────────────────────
@cli.group()
def video() -> None:
    """Generate and translate avatar videos."""


def _submit(payload: dict, wait: bool, timeout: int, output: Path | None) -> None:
    accepted = request("POST", "/api/v1/generate-avatar-video", json=payload)
    if not wait:
        emit(accepted)
    status = wait_for_job(accepted["job_id"], timeout)
    if output and status.get("video_url"):
        _download(status["video_url"], output)
        status["saved_to"] = str(output)
    emit(status)


@video.command("generate")
@click.option("--file", "file_", type=click.Path(exists=True, path_type=Path),
              help="Full scene-graph JSON (see examples/request.json)")
@click.option("--script", help="Shortcut: single-scene text instead of --file")
@click.option("--avatar-id", help="Required with --script")
@click.option("--voice-id", help="Required with --script")
@click.option("--language", default="en", show_default=True)
@click.option("--emotion", default="neutral", show_default=True,
              type=click.Choice(["neutral", "friendly", "serious", "excited", "sad"]))
@click.option("--test", "test_mode", is_flag=True, help="540p fast path, visible watermark")
@click.option("--wait/--no-wait", default=True, show_default=True)
@click.option("--timeout", default=1800, show_default=True, help="seconds to wait")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="save MP4 here when done")
def video_generate(file_, script, avatar_id, voice_id, language, emotion,
                   test_mode, wait, timeout, output) -> None:
    if file_:
        payload = json.loads(file_.read_text(encoding="utf-8"))
    elif script:
        if not (avatar_id and voice_id):
            die("--script requires --avatar-id and --voice-id", EXIT_USAGE)
        payload = {
            "title": "cli-generate",
            "scenes": [{
                "avatar": {"avatar_id": avatar_id},
                "voice": {"voice_id": voice_id, "input_text": script,
                          "language": language, "emotion": emotion},
            }],
        }
    else:
        die("provide --file or --script", EXIT_USAGE)
    payload["test_mode"] = test_mode or payload.get("test_mode", False)
    _submit(payload, wait, timeout, output)


@video.command("translate")
@click.option("--file", "file_", required=True, type=click.Path(exists=True, path_type=Path),
              help="Existing scene-graph JSON to re-dub")
@click.option("--language", required=True, help="Target ISO 639-1 code, e.g. es, de, ja")
@click.option("--translate-text/--keep-text", default=False, show_default=True,
              help="--keep-text assumes input_text is already in the target language; "
                   "--translate-text requires a configured translator and is TODO")
@click.option("--wait/--no-wait", default=True, show_default=True)
@click.option("--timeout", default=1800, show_default=True)
@click.option("-o", "--output", type=click.Path(path_type=Path))
def video_translate(file_, language, translate_text, wait, timeout, output) -> None:
    payload = json.loads(file_.read_text(encoding="utf-8"))
    if translate_text:
        die("machine translation of input_text is not wired up yet — "
            "translate the script first and use --keep-text", EXIT_USAGE)
    for scene in payload.get("scenes", []):
        scene["voice"]["language"] = language
    payload["title"] = f"{payload.get('title', 'untitled')} [{language}]"
    _submit(payload, wait, timeout, output)


# ────────────────────────── job ──────────────────────────
@cli.group()
def job() -> None:
    """Inspect, await, and download jobs."""


@job.command("status")
@click.argument("job_id")
def job_status(job_id: str) -> None:
    emit(request("GET", f"/api/v1/jobs/{job_id}"))


@job.command("wait")
@click.argument("job_id")
@click.option("--timeout", default=1800, show_default=True)
def job_wait(job_id: str, timeout: int) -> None:
    emit(wait_for_job(job_id, timeout))


@job.command("download")
@click.argument("job_id")
@click.option("-o", "--output", required=True, type=click.Path(path_type=Path))
def job_download(job_id: str, output: Path) -> None:
    status = request("GET", f"/api/v1/jobs/{job_id}")
    if status["status"] != "completed" or not status.get("video_url"):
        emit(status, api.EXIT_FAILED)
    _download(status["video_url"], output)
    status["saved_to"] = str(output)
    emit(status)


def _download(url: str, output: Path) -> None:
    info(f"downloading → {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=300) as r, output.open("wb") as f:
        for chunk in r.iter_bytes(1 << 20):
            f.write(chunk)


if __name__ == "__main__":
    cli()
