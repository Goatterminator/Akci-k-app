#!/usr/bin/env bash
# Akciók app telepítő Raspberry Pi-re (Raspberry Pi OS / Debian).
# Használat a repó mappájából:   bash deploy/install.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="${SUDO_USER:-$USER}"
SERVICE=/etc/systemd/system/akciok.service

port_busy() {
  # Igaz, ha valami már figyel az adott TCP porton (pl. egy másik projekted).
  if command -v ss >/dev/null; then
    [ -n "$(ss -ltnH "sport = :$1" 2>/dev/null)" ]
  else
    ! python3 -c "import socket,sys; s=socket.socket(); s.bind(('0.0.0.0', int(sys.argv[1])))" "$1" 2>/dev/null
  fi
}

# Port választás: 1) PORT=... környezeti változó, 2) korábbi telepítés .env-je, 3) első szabad 8080-tól.
# Így nem ütközik a Pi-n már futó más projektekkel.
if [ -n "${PORT:-}" ]; then
  CHOSEN="$PORT"
elif [ -f "$APP_DIR/.env" ] && grep -q '^PORT=[0-9]' "$APP_DIR/.env"; then
  CHOSEN="$(grep '^PORT=' "$APP_DIR/.env" | head -1 | cut -d= -f2)"
else
  CHOSEN=""
fi
# a saját, már futó példányunkat ne tekintsük ütközésnek (újratelepítés)
if systemctl is-active --quiet akciok.service 2>/dev/null; then
  sudo systemctl stop akciok.service
fi
if [ -n "$CHOSEN" ] && port_busy "$CHOSEN"; then
  echo "!! A(z) $CHOSEN port már foglalt (valószínűleg egy másik projekted használja)."
  if [ -n "${PORT:-}" ]; then
    echo "   Adj meg másikat, pl.:  PORT=8090 bash deploy/install.sh"; exit 1
  fi
  CHOSEN=""
fi
if [ -z "$CHOSEN" ]; then
  for p in $(seq 8080 8099); do
    if ! port_busy "$p"; then CHOSEN="$p"; break; fi
  done
fi
[ -z "$CHOSEN" ] && { echo "Nem találtam szabad portot 8080-8099 között. Adj meg egyet: PORT=9123 bash deploy/install.sh"; exit 1; }
PORT="$CHOSEN"

echo "==> Akciók app telepítése ide: $APP_DIR (felhasználó: $APP_USER, port: $PORT)"

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
  echo "==> .env létrehozva (a Gemini kulcsot a webes felületen is megadhatod)"
fi
if grep -q '^PORT=' "$APP_DIR/.env"; then
  sed -i "s/^PORT=.*/PORT=$PORT/" "$APP_DIR/.env"
else
  echo "PORT=$PORT" >> "$APP_DIR/.env"
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
  echo "==> HTTPS (nem kötelező; telefonos app-telepítéshez kell)"
  echo "    A telepítő a 'tailscale serve' beállításodhoz NEM nyúl, mert azon már"
  echo "    futhatnak más projektjeid. A mostani beállításod:"
  SERVE_STATUS="$(sudo tailscale serve status 2>/dev/null || true)"
  if [ -n "$SERVE_STATUS" ]; then
    echo "$SERVE_STATUS" | sed 's/^/      /'
  else
    echo "      (nincs beállítva)"
  fi
  # olyan HTTPS port, ami még nincs használatban a serve-ben
  HTTPS_PORT=""
  for hp in 8443 10000 9443 7443; do
    if ! echo "$SERVE_STATUS" | grep -q ":$hp\b"; then HTTPS_PORT="$hp"; break; fi
  done
  echo
  echo "    Hogy a többi projekted megmaradjon, KÜLÖN HTTPS portot használj:"
  echo "      sudo tailscale serve --bg --https=$HTTPS_PORT http://127.0.0.1:$PORT"
  [ -n "$TS_NAME" ] && echo "    Utána:  https://$TS_NAME:$HTTPS_PORT"
  echo "    Visszavonás:  sudo tailscale serve --https=$HTTPS_PORT off"
  echo "    (NE futtasd a sima 'tailscale serve --bg $PORT' parancsot: az a 443-as"
  echo "     porton lévő meglévő beállítást cserélné le!)"
fi
echo
echo "Nyisd meg a böngészőben: az ELSŐ regisztrált felhasználó lesz az admin."
echo "Naplók: journalctl -u akciok -f"
