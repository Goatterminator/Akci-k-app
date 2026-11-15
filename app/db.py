"""SQLite adatbázis réteg (stdlib sqlite3, WAL módban)."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    store         TEXT NOT NULL,
    title         TEXT NOT NULL,
    title_norm    TEXT NOT NULL,
    category      TEXT NOT NULL DEFAULT 'egyeb',
    subcategory   TEXT,
    kind          TEXT NOT NULL DEFAULT 'deal',
    price         REAL,
    old_price     REAL,
    discount_pct  REAL,
    price_huf     REAL,
    old_price_huf REAL,
    currency      TEXT NOT NULL DEFAULT 'HUF',
    unit_price    REAL,
    unit          TEXT,
    image         TEXT,
    url           TEXT,
    valid_from    TEXT,
    valid_to      TEXT,
    badge         TEXT,
    description   TEXT,
    product_key   TEXT,
    extra         TEXT,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_items_active_disc ON items(active, discount_pct DESC);
CREATE INDEX IF NOT EXISTS ix_items_source ON items(source, active);
CREATE INDEX IF NOT EXISTS ix_items_product ON items(product_key);
CREATE INDEX IF NOT EXISTS ix_items_category ON items(category, active);

CREATE TABLE IF NOT EXISTS price_history (
    item_id   TEXT NOT NULL,
    day       TEXT NOT NULL,
    price     REAL,
    old_price REAL,
    PRIMARY KEY (item_id, day)
);

CREATE TABLE IF NOT EXISTS sources (
    name      TEXT PRIMARY KEY,
    last_run  TEXT,
    last_ok   TEXT,
    ok        INTEGER,
    count     INTEGER,
    error     TEXT,
    duration  REAL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL UNIQUE COLLATE NOCASE,
    pw_hash     TEXT NOT NULL,
    is_admin    INTEGER NOT NULL DEFAULT 0,
    ntfy_topic  TEXT,
    ai_limit    INTEGER,          -- egyedi napi AI-keret (NULL = a közös beállítás)
    created     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token     TEXT PRIMARY KEY,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created   TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS favorites (
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id  TEXT NOT NULL,
    added    TEXT NOT NULL,
    PRIMARY KEY (user_id, item_id)
);

CREATE TABLE IF NOT EXISTS watches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    query        TEXT NOT NULL,
    max_price    REAL,
    min_discount REAL,
    category     TEXT,
    created      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
    item_id  TEXT NOT NULL,
    created  TEXT NOT NULL,
    seen     INTEGER NOT NULL DEFAULT 0,
    UNIQUE (watch_id, item_id)
);

CREATE TABLE IF NOT EXISTS ai_usage (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day     TEXT NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

CREATE TABLE IF NOT EXISTS cache (
    key     TEXT PRIMARY KEY,
    value   TEXT,
    created TEXT NOT NULL
);
"""

_init_lock = threading.Lock()
_initialized_path: str | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Régebbi adatbázisok bővítése új oszlopokkal (a meglévő adatok megmaradnak)."""
    user_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if "ai_limit" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN ai_limit INTEGER")


def init_db() -> None:
    global _initialized_path
    with _init_lock:
        conn = _connect()
        try:
            conn.executescript(SCHEMA)
            _migrate(conn)
            for key, value in config.DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value)
                )
            # Ha a .env-ben van Gemini kulcs, de az adatbázisban még üres, átvesszük.
            env_key = config.DEFAULT_SETTINGS.get("gemini_api_key")
            if env_key:
                conn.execute(
                    "UPDATE settings SET value=? WHERE key='gemini_api_key' AND (value IS NULL OR value='')",
                    (env_key,),
                )
            conn.commit()
        finally:
            conn.close()
        _initialized_path = str(config.DB_PATH)


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    if _initialized_path != str(config.DB_PATH):
        init_db()
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------- settings
def get_settings() -> dict[str, str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    out = dict(config.DEFAULT_SETTINGS)
    out.update({r["key"]: r["value"] or "" for r in rows})
    return out


def get_setting(key: str, default: str = "") -> str:
    return get_settings().get(key, default) or default


def set_settings(values: dict[str, Any]) -> None:
    with get_conn() as conn:
        for key, value in values.items():
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, "" if value is None else str(value)),
            )


# ---------------------------------------------------------------- cache
def cache_get(key: str, max_age_s: float | None = None) -> Any | None:
    with get_conn() as conn:
        row = conn.execute("SELECT value, created FROM cache WHERE key=?", (key,)).fetchone()
    if not row:
        return None
    if max_age_s is not None:
        created = datetime.fromisoformat(row["created"])
        if (datetime.now(timezone.utc) - created).total_seconds() > max_age_s:
            return None
    return json.loads(row["value"])


def cache_set(key: str, value: Any) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO cache(key, value, created) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, created=excluded.created",
            (key, json.dumps(value, ensure_ascii=False), now_iso()),
        )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    if "extra" in d:
        try:
            d["extra"] = json.loads(d["extra"]) if d["extra"] else {}
        except (TypeError, ValueError):
            d["extra"] = {}
    d.pop("title_norm", None)
    d.pop("rn", None)
    return d
