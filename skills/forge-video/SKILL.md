---
name: forge-video
description: Turn a script or idea into an avatar video (MP4) on a self-hosted AvatarForge stack. Use when the user wants to generate a talking-head video, product demo narration, or send a video message. Requires a registered twin from forge-avatar.
---

# forge-video — script → broadcast MP4

Generates avatar video through the AvatarForge gateway
(`POST /api/v1/generate-avatar-video`). Read the twin's IDs from the
project's `AVATAR-<NAME>.md` (created by [[forge-avatar]]).

## Quick path — single scene

```bash
forge video generate \
  --script "Hey team — quick update on the Q3 launch." \
  --avatar-id a1b2c3d4e5f6 --voice-id f6e5d4c3b2a1 \
  --language en --emotion friendly \
  --test -o ./preview.mp4
```

`--test` renders 540p with a visible watermark in a fraction of the time —
ALWAYS preview in test mode before a full render. Drop `--test` for the
final 1080p broadcast pass.

## Full path — multi-scene scene graph

Author a JSON scene graph (schema: `services/gateway/app/schemas.py`,
example: `examples/request.json`), then:

```bash
forge video generate --file ./video.json -o ./final.mp4
```

Scene graph capabilities:
- `scenes[]` — each binds one avatar + one voice track
- `avatar.position/scale` — normalized canvas placement; `matting: greenscreen`
  to key the avatar over any background
- `background` — hex color, image, or looping video
- `overlays[]` — timed text layers
- `transition` — `cut | fade | wipeleft | slideright`
- `voice.emotion` — `neutral | friendly | serious | excited | sad`
- `voice.speed` (0.5–2.0), `voice.pitch_semitones` (−6…+6)

## Script-writing guidance

- Write for the ear: short sentences, contractions, no bullet lists.
- ~150 words ≈ 1 minute of speech.
- Put emphasis words in their own short sentence rather than CAPS.
- Split scenes at topic changes; one scene per 30–60 s keeps sync tight.

## Job control

`--wait` (default) polls to completion; `--no-wait` returns the `job_id`
immediately for `forge job status|wait|download`. Exit code 3 = render
failed (inspect `.error` in the JSON), 4 = timeout.
