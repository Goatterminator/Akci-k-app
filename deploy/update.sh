#!/usr/bin/env bash
# Frissítés a legújabb verzióra:  bash deploy/update.sh
# (Az adatok – fiókok, beállítások, akciók – megmaradnak.)
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

echo "==> Új verzió letöltése"
if ! git pull --ff-only; then
  echo "!! A letöltés nem sikerült. Ha a Pi-n kézzel módosítottál fájlt, ez okozhatja:"
  git status --short | grep -v '^??' || true
  echo "   Megoldás: git stash   (majd futtasd újra ezt a scriptet)"
  exit 1
fi
echo "    Verzió: $(git log -1 --format='%h – %s')"

echo "==> Függőségek"
"$APP_DIR/.venv/bin/pip" install -q -r requirements.txt

echo "==> Újraindítás"
sudo systemctl restart akciok.service

PORT="$(grep '^PORT=' "$APP_DIR/.env" 2>/dev/null | head -1 | cut -d= -f2)"
PORT="${PORT:-8090}"
for i in $(seq 1 20); do
  sleep 1
  if curl -fsS "http://127.0.0.1:$PORT/api/auth/state" >/dev/null 2>&1; then
    echo "Kész: frissítve és újraindítva, az app fut a $PORT porton. Frissítsd az oldalt a böngészőben."
    exit 0
  fi
done
echo "!! Az app nem indult el az újraindítás után. Az utolsó naplósorok:"
sudo journalctl -u akciok --no-pager -n 30
exit 1
