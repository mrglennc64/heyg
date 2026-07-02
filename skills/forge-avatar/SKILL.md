---
name: forge-avatar
description: Create a persistent digital twin on a self-hosted AvatarForge stack — register a face (15 s base video or portrait photo) and a cloned voice (30 s–3 min sample plus a recorded consent clip). Use when the user wants to create an avatar, digital twin, or clone their voice for video generation.
---

# forge-avatar — give the agent a face and a voice

Registers reusable identity assets against a self-hosted AvatarForge gateway.
Run once per person; the returned IDs are used by [[forge-video]] and
[[forge-translate]] forever after.

## Prerequisites

- `forge` CLI on PATH (`pipx install ./cli` from the repo root)
- `FORGE_BASE_URL` (default `http://localhost:8000`) and `FORGE_API_KEY` set
- All output is JSON on stdout; exit codes: 0 ok, 1 API error, 2 usage,
  3 failed, 4 timeout

## Register the face

Best results: a ~15 second video, subject facing camera, neutral idle motion
(slight sway, blinking, closed mouth), even lighting, no cuts.

```bash
forge avatar create --name "Glenn" --media ./glenn_base.mp4 --kind base_video
# → {"avatar_id": "a1b2c3d4e5f6", ...}
```

A single photo also works (`--kind still_portrait`), at lower realism —
head motion is then synthesized by SadTalker.

## Register the voice (consent is mandatory)

Two recordings are required:

1. `--sample`: 30 seconds to 3 minutes of clean, single-speaker speech.
   Varied delivery (calm + animated sentences) improves emotion control.
2. `--consent`: the same speaker reading, in their own voice:
   *"I consent to my voice being cloned for video generation on this system."*
   The API refuses cloning without it (HTTP 403).

```bash
forge voice create --name "Glenn" --sample ./glenn_voice.wav --consent ./glenn_consent.wav
# → {"voice_id": "f6e5d4c3b2a1", ...}
```

## Persist the twin for other skills

After registration, write an `AVATAR-<NAME>.md` in the project root so any
agent can rediscover the twin without re-asking:

```markdown
# AVATAR-GLENN
avatar_id: a1b2c3d4e5f6
voice_id: f6e5d4c3b2a1
kind: base_video
languages_verified: [en, es]
```

## Rules

- Never clone a voice or face without the subject's explicit permission.
- One twin per `AVATAR-*.md` file; update in place, don't duplicate.
