"""Alap konfiguráció: környezeti változók + .env fájl.

A futás közben módosítható beállítások (Gemini kulcs, ntfy topic, stb.)
az adatbázis `settings` táblájában vannak, lásd `app.db.get_setting`.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
if not DATA_DIR.is_absolute():
    DATA_DIR = (BASE_DIR / DATA_DIR).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "akciok.db"
STATIC_DIR = BASE_DIR / "static"

PORT = int(os.environ.get("PORT", "8080"))
HOST = os.environ.get("HOST", "0.0.0.0")

# Ha "0", a háttérfrissítés nem indul el (tesztekhez hasznos).
AUTO_REFRESH = os.environ.get("AUTO_REFRESH", "1") != "0"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

# Alapértelmezett, a felületen átírható beállítások.
DEFAULT_SETTINGS: dict[str, str] = {
    "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
    "gemini_model": os.environ.get("GEMINI_MODEL", "gemini-flash-latest"),
    "refresh_hours": "6",
    "eur_huf": "390",
    "ntfy_server": "https://ntfy.sh",
    "ntfy_topic": "",
    "disabled_sources": "",
    "min_discount_feed": "10",
    "emag_urls": "",
}
