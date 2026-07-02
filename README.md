# AvatarForge — Open-Source HeyGen Alternative

Self-hosted text-to-video avatar platform: voice cloning (XTTS v2), talking-head
neural rendering (LivePortrait / SadTalker), multi-language lip-sync dubbing
(MuseTalk) with dynamic alpha masking, and an FFmpeg canvas compositor behind a
HeyGen-style FastAPI.

## System Architecture

```
                         ┌──────────────────────────────────────────────┐
                         │  web/ (Next.js Canvas Editor)                │
                         └──────────────┬───────────────────────────────┘
                                        │ JSON scene graph
                         ┌──────────────▼───────────────────────────────┐
                         │  gateway (FastAPI)  :8000                    │
                         │  /api/v1/generate-avatar-video               │
                         │  Postgres (jobs/assets) · MinIO (artifacts)  │
                         └──────────────┬───────────────────────────────┘
                                        │ Celery over Redis
        ┌───────────────────┬───────────┴────────────┬────────────────────┐
        ▼                   ▼                        ▼                    ▼
┌──────────────┐   ┌────────────────┐   ┌────────────────────┐   ┌──────────────┐
│ voice        │   │ avatar         │   │ lipsync            │   │ compositor   │
│ XTTS v2      │──▶│ LivePortrait / │──▶│ MuseTalk + dynamic │──▶│ FFmpeg canvas│
│ clone + TTS  │   │ SadTalker      │   │ alpha jaw masking  │   │ → MP4        │
│ GPU 0        │   │ GPU 1          │   │ GPU 1              │   │ CPU / NVENC  │
└──────────────┘   └────────────────┘   └────────────────────┘   └──────────────┘
```

### Job lifecycle (per scene, Celery chain → chord)

1. **voice.synthesize** — XTTS v2, speaker latents cached per voice_id,
   sentence-chunked synthesis, crossfaded, loudness-normalized (EBU R128).
2. **avatar.drive** — builds the body-motion track: ping-pong loops the 15 s
   base video to audio length (seam-free long-form stability), or SadTalker
   audio→motion for static portraits.
3. **lipsync.dub** — MuseTalk inpaints only the mouth region; a feathered,
   landmark-tracked alpha mask + LAB color transfer preserves original
   lighting, skin tone, and clothing.
4. **compositor.render** — chord over all scenes: background, avatar
   placement/scale, overlays, captions, xfade transitions → broadcast MP4
   (H.264 High, yuv420p, BT.709, AAC 192k, loudnorm).

## Directory structure

```
heygen/
├── README.md
├── docker-compose.yml
├── .env.example
├── Makefile
├── shared/                          # installed into every service image
│   └── forge_shared/
│       ├── __init__.py
│       ├── config.py                # env-driven settings (pydantic-settings)
│       ├── storage.py               # MinIO/S3 artifact store
│       ├── queue.py                 # Celery app factory + queue routing
│       └── contracts.py             # cross-service pydantic payloads
├── services/
│   ├── gateway/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── app/
│   │       ├── main.py              # FastAPI app, lifespan, routers
│   │       ├── db.py                # async SQLAlchemy engine/session
│   │       ├── models.py            # Job / Avatar / Voice ORM
│   │       ├── schemas.py           # HeyGen-style request/response schema
│   │       ├── orchestrator.py      # scene graph → Celery canvas
│   │       └── routers/
│   │           ├── generate.py      # POST /api/v1/generate-avatar-video
│   │           ├── voices.py        # voice sample upload + clone registration
│   │           └── avatars.py       # base video / portrait registration
│   ├── voice/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── worker/
│   │       ├── tasks.py             # celery task: voice.synthesize
│   │       ├── xtts_engine.py       # XTTS v2 wrapper, latent cache, chunking
│   │       └── audio_post.py        # pitch shift, crossfade, loudnorm
│   ├── avatar/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── worker/
│   │       ├── tasks.py             # celery task: avatar.drive
│   │       ├── motion_engine.py     # LivePortrait retarget / SadTalker still
│   │       └── stabilizer.py        # ping-pong looping, drift correction
│   ├── lipsync/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── worker/
│   │       ├── tasks.py             # celery task: lipsync.dub
│   │       ├── musetalk_engine.py   # MuseTalk inference wrapper
│   │       └── masking.py           # landmark-tracked feathered alpha mask
│   └── compositor/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── worker/
│           ├── tasks.py             # celery task: compositor.render
│           └── ffmpeg_canvas.py     # scene graph → filter_complex → MP4
├── web/                             # Next.js canvas editor (drag-position studio)
├── cli/                             # `forge` CLI — pipx install ./cli
│   └── forge_cli/                   # JSON on stdout, stable exit codes
├── skills/                          # agent skills (mirrors heygen-com/skills)
│   ├── forge-avatar/SKILL.md        # register face + consent-gated voice clone
│   ├── forge-video/SKILL.md         # script → MP4 via CLI or scene graph
│   └── forge-translate/SKILL.md     # re-dub scene graph into 17 languages
├── infra/
│   ├── postgres/init.sql
│   └── models/download_models.sh    # pulls XTTS/LivePortrait/MuseTalk weights
└── data/                            # bind mounts: models, artifacts (gitignored)
```

## Quick start

```bash
cp .env.example .env
bash infra/models/download_models.sh    # ~12 GB of weights into ./data/models
docker compose up -d --build
curl -X POST http://localhost:8000/api/v1/generate-avatar-video \
     -H "Content-Type: application/json" -H "X-Api-Key: $FORGE_API_KEY" \
     -d @examples/request.json
```

## GPU layout

| Service    | Model            | VRAM (fp16) | Default device |
|------------|------------------|-------------|----------------|
| voice      | XTTS v2          | ~4 GB       | GPU 0          |
| avatar     | LivePortrait     | ~6 GB       | GPU 1          |
| lipsync    | MuseTalk 1.5     | ~6 GB       | GPU 1          |
| compositor | FFmpeg (+NVENC)  | —           | GPU 0 (encode) |

Single-GPU hosts: set all `device_ids` to `"0"` in docker-compose and lower
`WORKER_CONCURRENCY` to 1 — the queue serializes stages so peak VRAM stays
bounded.

## Ethics / provenance (non-optional)

- **Consent gate**: `/api/v1/voices` requires a recorded consent phrase and
  stores its hash; cloning without it returns 403.
- **Watermark**: compositor embeds an invisible watermark + C2PA-style
  provenance metadata in every output. Do not remove.
- Only clone voices/faces of people who gave you explicit permission.
