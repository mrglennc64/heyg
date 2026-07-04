#!/usr/bin/env bash
# MuseTalk 1.5 install into a dedicated venv on /workspace (survives pod stops).
# Isolated because the mm* stack pins an older torch than the service env.
# HARD RULE: abort rather than ever run pip against the system python.
set -uo pipefail
cd /workspace
mkdir -p venvs

apt-get install -y -qq python3.10-venv python3-venv >/dev/null 2>&1 || true
PY=$(command -v python3.10 || command -v python3)
echo "using $PY"
rm -rf venvs/mt
$PY -m venv venvs/mt || { echo "XX venv creation failed"; exit 1; }
[ -f venvs/mt/bin/activate ] || { echo "XX no activate — venv broken"; exit 1; }
source venvs/mt/bin/activate
[ "$(command -v python)" = "/workspace/venvs/mt/bin/python" ] || { echo "XX venv not active"; exit 1; }
python -m pip install -q --upgrade pip wheel setuptools

echo "=== torch cu118 (mm* wheels exist for this combo) ==="
python -m pip install -q torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 \
  --index-url https://download.pytorch.org/whl/cu118 || { echo "XX torch install failed"; exit 1; }

echo "=== MuseTalk repo ==="
[ -d MuseTalk ] || git clone -q https://github.com/TMElyralab/MuseTalk.git
cd MuseTalk

echo "=== python deps ==="
python -m pip install -q -r requirements.txt || { echo "XX requirements failed"; exit 1; }
# transformers in requirements needs an older hub API (found live 2026-07-04)
python -m pip install -q "huggingface-hub==0.25.2"
python -m pip install -q -U openmim
# chumpy (mmpose dep) predates PEP 517 — its isolated build env has no pip
python -m pip install -q setuptools wheel numpy
python -m pip install -q --no-build-isolation chumpy==0.70
mim install -q mmengine "mmcv==2.0.1" "mmdet==3.1.0" "mmpose==1.1.0" || { echo "XX mm* install failed"; exit 1; }

echo "=== weights (~4 GB, explicit URLs — download_weights.sh fetched nothing on 2026-07-04) ==="
cd models
dl() { [ -s "$1" ] || curl -sL -o "$1" "$2" || echo "!! failed: $1"; }
dl musetalkV15/unet.pth        https://huggingface.co/TMElyralab/MuseTalk/resolve/main/musetalkV15/unet.pth
dl musetalkV15/musetalk.json   https://huggingface.co/TMElyralab/MuseTalk/resolve/main/musetalkV15/musetalk.json
dl sd-vae/config.json          https://huggingface.co/stabilityai/sd-vae-ft-mse/resolve/main/config.json
dl sd-vae/diffusion_pytorch_model.bin https://huggingface.co/stabilityai/sd-vae-ft-mse/resolve/main/diffusion_pytorch_model.bin
dl whisper/config.json         https://huggingface.co/openai/whisper-tiny/resolve/main/config.json
dl whisper/pytorch_model.bin   https://huggingface.co/openai/whisper-tiny/resolve/main/pytorch_model.bin
dl whisper/preprocessor_config.json https://huggingface.co/openai/whisper-tiny/resolve/main/preprocessor_config.json
dl dwpose/dw-ll_ucoco_384.pth  https://huggingface.co/yzd-v/DWPose/resolve/main/dw-ll_ucoco_384.pth
dl face-parse-bisent/79999_iter.pth https://huggingface.co/ManyOtherFunctions/face-parse-bisent/resolve/main/79999_iter.pth
dl face-parse-bisent/resnet18-5c106cde.pth https://download.pytorch.org/models/resnet18-5c106cde.pth
cd ..
du -sh models/*/ 2>/dev/null

echo "=== smoke: imports on venv python ==="
python - <<'PY'
import torch, mmpose, diffusers
print("cuda:", torch.cuda.is_available(), "| torch", torch.__version__)
print("MUSETALK-IMPORTS-OK")
PY
echo MUSETALK-SETUP-DONE
