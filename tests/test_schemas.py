"""Offline contract tests — no Docker, no GPU, no network.

Validates that:
1. examples/request.json parses against the gateway's VideoRequest schema
2. schema guardrails actually reject bad input
3. gateway scene graph normalizes into the inter-service wire contracts
4. the CLI's quick-path payload is schema-valid

Run:  python tests/test_schemas.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "gateway"))
sys.path.insert(0, str(ROOT / "shared"))

from pydantic import ValidationError

from app.schemas import VideoRequest  # gateway public schema
from forge_shared.contracts import TTSRequest, LipsyncRequest

PASS, FAIL = 0, 0


def check(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  ok  {name}")
    except Exception as exc:  # noqa: BLE001
        FAIL += 1
        print(f"FAIL  {name}: {exc}")


def expect_invalid(payload: dict) -> None:
    try:
        VideoRequest(**payload)
    except ValidationError:
        return
    raise AssertionError("schema accepted invalid payload")


# ── 1. the shipped example must be valid ──────────────────────────
example = json.loads((ROOT / "examples" / "request.json").read_text(encoding="utf-8"))
check("examples/request.json validates", lambda: VideoRequest(**example))

req = VideoRequest(**example)
check("two scenes parsed", lambda: (_ for _ in ()).throw(AssertionError) if len(req.scenes) != 2 else None)
check("greenscreen matting round-trips", lambda: None if req.scenes[0].avatar.matting == "greenscreen" else (_ for _ in ()).throw(AssertionError))
check("spanish voice track round-trips", lambda: None if req.scenes[0].voice.language == "es" else (_ for _ in ()).throw(AssertionError))

# ── 2. guardrails reject bad input ────────────────────────────────
base_scene = req.scenes[0].model_dump()

def mutated(path: list, value):
    p = json.loads(json.dumps({"scenes": [base_scene]}))
    node = p["scenes"][0]
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    return p

check("rejects odd dimensions (yuv420p)", lambda: expect_invalid({**example, "dimension": {"width": 1919, "height": 1080}}))
check("rejects empty scene list", lambda: expect_invalid({**example, "scenes": []}))
check("rejects fps=23", lambda: expect_invalid({**example, "fps": 23}))
check("rejects position x=1.5", lambda: expect_invalid(mutated(["avatar", "position", "x"], 1.5)))
check("rejects speed=3.0", lambda: expect_invalid(mutated(["voice", "speed"], 3.0)))
check("rejects pitch=+12 st", lambda: expect_invalid(mutated(["voice", "pitch_semitones"], 12)))
check("rejects unknown emotion", lambda: expect_invalid(mutated(["voice", "emotion"], "furious")))
check("rejects empty script", lambda: expect_invalid(mutated(["voice", "input_text"], "")))

# ── 3. gateway → wire contract normalization ──────────────────────
def normalize():
    s = req.scenes[0]
    TTSRequest(
        job_id="j1", scene_id=s.scene_id, voice_id=s.voice.voice_id,
        text=s.voice.input_text, language=s.voice.language,
        speed=s.voice.speed, pitch_semitones=s.voice.pitch_semitones,
        emotion=s.voice.emotion,
    )
    LipsyncRequest(job_id="j1", scene_id=s.scene_id, video_key="k", audio_key="k")

check("scene normalizes into TTS + lipsync wire contracts", normalize)

# ── 4. CLI quick-path payload is schema-valid ─────────────────────
cli_payload = {
    "title": "cli-generate",
    "scenes": [{
        "avatar": {"avatar_id": "a" * 12},
        "voice": {"voice_id": "b" * 12, "input_text": "Hello world.",
                  "language": "en", "emotion": "friendly"},
    }],
    "test_mode": True,
}
check("CLI --script shortcut payload validates", lambda: VideoRequest(**cli_payload))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
