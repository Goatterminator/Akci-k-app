#!/usr/bin/env bash
# Frissítés a legújabb verzióra:  bash deploy/update.sh
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"
git pull --ff-only
"$APP_DIR/.venv/bin/pip" install -r requirements.txt
sudo systemctl restart akciok.service
echo "Frissítve és újraindítva."
