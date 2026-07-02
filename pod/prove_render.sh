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
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
fetch(){ # fetch <dest> <url...> — try each url until one works
  local dest="$1"; shift
  [ -s "$dest" ] && { echo "  cached: $dest"; return 0; }
  for u in "$@"; do
    echo "  trying: $u"
    if curl -fL --retry 3 -A "$UA" -o "$dest" "$u" && [ -s "$dest" ]; then echo "  ok -> $dest"; return 0; fi
  done
  return 1
}
fetch_face(){ # download a REAL face image (validate it decodes as an image)
  rm -f face.jpg
  for u in "$@"; do
    echo "  trying face: $u"
    curl -fL --retry 3 -A "$UA" -o face.jpg "$u" 2>/dev/null || { rm -f face.jpg; continue; }
    if python -c "import cv2,sys; sys.exit(0 if cv2.imread('face.jpg') is not None else 1)" 2>/dev/null; then
      echo "  ok -> face.jpg ($(du -h face.jpg | cut -f1), valid image)"; return 0
    fi
    echo "  (not a valid image, trying next)"; rm -f face.jpg
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

log "5. torch 2.x + librosa 0.10 compat patches"
# 5a. torch.load weights_only default changed in torch>=2.4 -> force False
grep -rl "torch.load" *.py face_detection 2>/dev/null | while read -r f; do
  sed -i 's/torch\.load(\([^)]*\))/torch.load(\1, weights_only=False)/g' "$f" 2>/dev/null || true
done
grep -rl "weights_only=False, weights_only=False" *.py face_detection 2>/dev/null | while read -r f; do
  sed -i 's/, weights_only=False, weights_only=False/, weights_only=False/g' "$f"
done
# 5b. librosa>=0.10 made sr/n_fft keyword-only in filters.mel()
sed -i 's/librosa\.filters\.mel(hp\.sample_rate, hp\.n_fft,/librosa.filters.mel(sr=hp.sample_rate, n_fft=hp.n_fft,/' audio.py
echo "  patched audio.py mel(): $(grep -c 'sr=hp.sample_rate' audio.py) call(s)"

log "6. inputs: face image + spoken audio"
fetch_face \
  "https://thispersondoesnotexist.com/" \
  "https://raw.githubusercontent.com/OpenTalker/SadTalker/main/examples/source_image/art_0.png" \
  "https://raw.githubusercontent.com/OpenTalker/SadTalker/main/examples/source_image/full_body_1.png" \
  || fail "could not fetch a valid face image — paste the log, I'll swap the URL"
SCRIPT="Hi! This talking avatar was generated end to end on a self hosted GPU. Voice synthesis, then neural lip sync, all open source. It works."
python -m edge_tts --voice en-US-JennyNeural --text "$SCRIPT" --write-media speech.mp3 2>&1 | tail -1
ffmpeg -y -loglevel error -i speech.mp3 -ar 16000 -ac 1 speech.wav || fail "audio convert failed"
echo "  audio ready: $(du -h speech.wav | cut -f1)"

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
