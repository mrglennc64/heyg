#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# AvatarForge — "prove it renders once" on a RunPod GPU.
# Minimal, reliable path:  edge-tts (speech)  →  Wav2Lip (GPU lip-sync)
# Output: /workspace/proof/proof.mp4   (download via the Jupyter file browser)
#
# Run in the pod's Jupyter terminal:
#   curl -fsSL https://raw.githubusercontent.com/mrglennc64/heyg/main/pod/prove_render.sh | bash 2>&1 | tee /workspace/proof.log
# Then paste me the last ~30 lines if anything fails.
# ─────────────────────────────────────────────────────────────────────────
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
WORK=/workspace/proof
mkdir -p "$WORK"; cd "$WORK"

log(){ echo -e "\n=== $* ==="; }
fail(){ echo "XX FAILED: $*"; exit 1; }
fetch(){ # fetch <dest> <url...> — try each url until one works
  local dest="$1"; shift
  [ -s "$dest" ] && { echo "  cached: $dest"; return 0; }
  for u in "$@"; do
    echo "  trying: $u"
    if curl -fL --retry 3 -o "$dest" "$u" && [ -s "$dest" ]; then echo "  ok -> $dest"; return 0; fi
  done
  return 1
}

log "0. environment"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || fail "no GPU"
python --version; echo "torch: $(python -c 'import torch;print(torch.__version__, torch.cuda.is_available())' 2>&1)"

log "1. system deps"
apt-get update -qq && apt-get install -y -qq ffmpeg git wget >/dev/null 2>&1 || echo "  (apt warnings ignored)"

log "2. python deps"
pip install -q edge-tts "numpy<2" "librosa==0.10.2" opencv-python-headless \
    "scipy" "numba" tqdm gdown 2>&1 | tail -2

log "3. Wav2Lip code"
[ -d Wav2Lip ] || git clone -q https://github.com/Rudrabha/Wav2Lip.git
cd Wav2Lip

log "4. model checkpoints"
mkdir -p checkpoints face_detection/detection/sfd
fetch checkpoints/wav2lip_gan.pth \
  "https://huggingface.co/camenduru/Wav2Lip/resolve/main/checkpoints/wav2lip_gan.pth" \
  "https://huggingface.co/numz/wav2lip_studio/resolve/main/Wav2lip/wav2lip_gan.pth" \
  || fail "could not fetch wav2lip_gan.pth — paste the log, I'll swap the URL"
fetch face_detection/detection/sfd/s3fd.pth \
  "https://huggingface.co/camenduru/Wav2Lip/resolve/main/checkpoints/s3fd.pth" \
  "https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth" \
  || fail "could not fetch s3fd face detector — paste the log, I'll swap the URL"

log "5. torch 2.x compat patch (weights_only default changed in torch>=2.4)"
# Wav2Lip calls torch.load without weights_only; force it False everywhere.
grep -rl "torch.load" *.py face_detection 2>/dev/null | while read -r f; do
  sed -i 's/torch\.load(\([^)]*\))/torch.load(\1, weights_only=False)/g' "$f" 2>/dev/null || true
done
# double-load guard produces weights_only=False, weights_only=False — collapse it
grep -rl "weights_only=False, weights_only=False" *.py face_detection 2>/dev/null | while read -r f; do
  sed -i 's/, weights_only=False, weights_only=False/, weights_only=False/g' "$f"
done

log "6. inputs: face image + spoken audio"
fetch face.jpg \
  "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2c/Rebecca_Ferguson_by_Gage_Skidmore.jpg/480px-Rebecca_Ferguson_by_Gage_Skidmore.jpg" \
  "https://raw.githubusercontent.com/Rudrabha/Wav2Lip/master/evaluation/test_filelists/README.md" \
  || fail "could not fetch a sample face image"
SCRIPT="Hi! This talking avatar was generated end to end on a self hosted GPU. Voice synthesis, then neural lip sync, all open source. It works."
python -m edge_tts --voice en-US-JennyNeural --text "$SCRIPT" --write-media speech.mp3 2>&1 | tail -1
ffmpeg -y -loglevel error -i speech.mp3 -ar 16000 -ac 1 speech.wav || fail "audio convert failed"
echo "  audio: $(du -h speech.wav | cut -f1)"

log "7. RENDER (Wav2Lip inference on GPU)"
python inference.py \
  --checkpoint_path checkpoints/wav2lip_gan.pth \
  --face face.jpg \
  --audio speech.wav \
  --outfile "$WORK/proof.mp4" \
  --pads 0 15 0 0 --resize_factor 1 --nosmooth 2>&1 | tail -25

if [ -s "$WORK/proof.mp4" ]; then
  log "SUCCESS"
  echo "Talking-avatar MP4 rendered:"
  ls -lh "$WORK/proof.mp4"
  ffprobe -v error -show_entries format=duration,size -of default=nw=1 "$WORK/proof.mp4" 2>/dev/null
  echo ""
  echo ">>> Download it from the Jupyter file browser:  proof/proof.mp4"
else
  fail "inference produced no output — paste the log from step 7"
fi
