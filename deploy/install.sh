#!/usr/bin/env bash
# Akciók app telepítő Raspberry Pi-re (Raspberry Pi OS / Debian).
# Használat a repó mappájából:   bash deploy/install.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="${SUDO_USER:-$USER}"
PORT="${PORT:-8080}"
SERVICE=/etc/systemd/system/akciok.service

echo "==> Akciók app telepítése ide: $APP_DIR (felhasználó: $APP_USER)"

if ! command -v python3 >/dev/null; then
  echo "Python 3 kell: sudo apt install -y python3 python3-venv"; exit 1
fi
if ! python3 -c "import venv" 2>/dev/null; then
  echo "==> python3-venv telepítése"
  sudo apt-get update && sudo apt-get install -y python3-venv
fi

echo "==> Virtuális környezet és függőségek"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip >/dev/null
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  sed -i "s/^PORT=.*/PORT=$PORT/" "$APP_DIR/.env"
  echo "==> .env létrehozva (a Gemini kulcsot a webes felületen is megadhatod)"
fi
chmod 600 "$APP_DIR/.env"

echo "==> systemd szolgáltatás: $SERVICE"
sudo tee "$SERVICE" >/dev/null <<UNIT
[Unit]
Description=Akciók app (budapesti akciófigyelő)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m app.main
Restart=on-failure
RestartSec=10
# Pi-barát korlátok
MemoryMax=300M
Nice=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now akciok.service
sleep 2
sudo systemctl --no-pager --lines=5 status akciok.service || true

echo
echo "==> Kész! Elérés:"
echo "    Helyi hálón:   http://$(hostname -I | awk '{print $1}'):$PORT"
if command -v tailscale >/dev/null; then
  TS_IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
  TS_NAME="$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || true)"
  [ -n "$TS_IP" ] && echo "    Tailscale-en:  http://$TS_IP:$PORT"
  [ -n "$TS_NAME" ] && echo "    MagicDNS:      http://${TS_NAME%%.*}:$PORT"
  echo
  echo "    HTTPS-hez (ajánlott, így telefonon appként is telepíthető):"
  echo "      sudo tailscale serve --bg $PORT"
  [ -n "$TS_NAME" ] && echo "      majd: https://$TS_NAME"
fi
echo
echo "Nyisd meg a böngészőben: az ELSŐ regisztrált felhasználó lesz az admin."
echo "Naplók: journalctl -u akciok -f"
