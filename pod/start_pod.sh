#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# Start the AvatarForge GPU render service on the pod + prep the VPS tunnel.
# Assumes prove_render.sh already ran (Wav2Lip + checkpoints in /workspace).
#
# Run (download-then-run so stdin stays clean):
#   curl -fsSL https://raw.githubusercontent.com/mrglennc64/heyg/main/pod/start_pod.sh -o /tmp/sp.sh && bash /tmp/sp.sh
# ─────────────────────────────────────────────────────────────────────────
set -uo pipefail
VPS=46.202.143.253
TUNNEL_PORT=18000        # VPS localhost port that maps to this pod's :8000

echo "=== 1. service deps ==="
pip install -q fastapi "uvicorn[standard]" python-multipart edge-tts 2>&1 | tail -1

echo "=== 2. voice cloning engine (Chatterbox) ==="
if pip install -q chatterbox-tts 2>&1 | tail -1; then
  # pre-download the multilingual weights so the first render doesn't eat
  # the request timeout (~4 GB from HuggingFace, cached in /workspace)
  export HF_HOME=/workspace/hf_cache
  python - <<'PY' || echo "!! chatterbox warm-up failed — cloned voices will fall back to edge-tts"
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
ChatterboxMultilingualTTS.from_pretrained(device="cuda")
print("chatterbox ready")
PY
else
  echo "!! chatterbox install failed — cloned voices will fall back to edge-tts"
fi

echo "=== 3. fetch render service ==="
curl -fsSL https://raw.githubusercontent.com/mrglennc64/heyg/main/pod/render_service.py \
  | tr -d '\r' > /workspace/render_service.py
[ -d /workspace/proof/Wav2Lip ] || { echo "XX Wav2Lip missing — run prove_render.sh first"; exit 1; }

echo "=== 4. start render service on 127.0.0.1:8000 ==="
pkill -f "uvicorn.*render_service" 2>/dev/null || true
cd /workspace
HF_HOME=/workspace/hf_cache nohup uvicorn render_service:app --host 127.0.0.1 --port 8000 > /workspace/render_service.log 2>&1 &
sleep 6
if curl -fsS http://127.0.0.1:8000/health; then echo; echo "  service UP"; else
  echo "XX service failed to start — tail log:"; tail -20 /workspace/render_service.log; exit 1; fi

echo "=== 5. tunnel key ==="
KEY=/root/.ssh/forge_tunnel
mkdir -p /root/.ssh
[ -f "$KEY" ] || ssh-keygen -t ed25519 -N "" -f "$KEY" -C "forge-pod-tunnel" >/dev/null
echo
echo ">>> SEND THIS PUBLIC KEY to your assistant so it can authorize the tunnel:"
echo "-------------------------------------------------------------------------"
cat "$KEY.pub"
echo "-------------------------------------------------------------------------"
echo
echo "After it confirms the key is added on the VPS, open the tunnel with:"
echo
echo "  ssh -N -R ${TUNNEL_PORT}:127.0.0.1:8000 -i $KEY \\"
echo "    -o StrictHostKeyChecking=no -o ExitOnForwardFailure=yes \\"
echo "    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 forgetunnel@${VPS}"
echo
echo "(keep that command running in this terminal — it's the live link to your app)"
