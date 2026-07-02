#!/usr/bin/env bash
# Pulls all model weights + vendored repos into ./data/models (~12 GB).
set -euo pipefail
MODELS="$(cd "$(dirname "$0")/../.." && pwd)/data/models"
mkdir -p "$MODELS"

echo "── XTTS v2 (Coqui) ──────────────────────────────────────"
mkdir -p "$MODELS/xtts_v2"
python -m pip install -q "huggingface_hub[cli]"
hf download coqui/XTTS-v2 --local-dir "$MODELS/xtts_v2"

echo "── MuseTalk 1.5 ─────────────────────────────────────────"
if [ ! -d "$MODELS/musetalk" ]; then
    git clone --depth 1 https://github.com/TMElyralab/MuseTalk "$MODELS/musetalk"
fi
hf download TMElyralab/MuseTalk --local-dir "$MODELS/musetalk/models"

echo "── SadTalker (still-portrait path) ──────────────────────"
if [ ! -d "$MODELS/sadtalker" ]; then
    git clone --depth 1 https://github.com/OpenTalker/SadTalker "$MODELS/sadtalker"
    bash "$MODELS/sadtalker/scripts/download_models.sh" || \
        echo "!! run SadTalker's model download inside the avatar container if this failed"
fi

echo "── LivePortrait (optional refinement) ───────────────────"
if [ ! -d "$MODELS/liveportrait" ]; then
    git clone --depth 1 https://github.com/KwaiVGI/LivePortrait "$MODELS/liveportrait"
    hf download KwaiVGI/LivePortrait --local-dir "$MODELS/liveportrait/pretrained_weights"
fi

echo "✔ all models in $MODELS"
