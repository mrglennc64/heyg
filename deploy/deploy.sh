#!/usr/bin/env bash
# One-shot VPS bootstrap for heyg.usesmpt.com (Ubuntu/Debian).
# Run as root on the VPS:  bash <(curl -fsSL https://raw.githubusercontent.com/mrglennc64/heyg/main/deploy/deploy.sh)
set -euo pipefail

REPO="https://github.com/mrglennc64/heyg.git"
DIR=/opt/avatarforge

echo "── installing docker ──"
if ! command -v docker >/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi

echo "── fetching code ──"
if [ -d "$DIR/.git" ]; then
    git -C "$DIR" pull --ff-only
else
    git clone "$REPO" "$DIR"
fi

echo "── starting stack (web + demo API + HTTPS) ──"
cd "$DIR"
docker compose -f deploy/docker-compose.prod.yml up -d --build

echo
echo "✔ done — https://heyg.usesmpt.com (TLS certificate provisions on first request)"
docker compose -f deploy/docker-compose.prod.yml ps
