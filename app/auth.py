"""Felhasználók és munkamenetek.

* Az ELSŐ regisztrált felhasználó automatikusan admin: csak ő látja a
  Beállításokat (Gemini API kulcs, források, frissítés, felhasználók).
* További felhasználók akkor regisztrálhatnak, ha az admin engedi.
* Jelszó: PBKDF2-SHA256 sóval; munkamenet: véletlen token httpOnly sütiben.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request

from . import db

COOKIE = "akciok_session"
SESSION_DAYS = 180
_ITERATIONS = 150_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def user_count() -> int:
    with db.get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def public_user(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "is_admin": bool(row["is_admin"]),
        "ntfy_topic": row["ntfy_topic"] or "",
        "created": row["created"],
    }


def create_user(username: str, password: str) -> dict[str, Any]:
    """Az első felhasználó admin lesz. Versenyhelyzet ellen egy tranzakcióban döntünk."""
    username = username.strip()
    with db.get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        first = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        if not first and db.get_setting("allow_registration", "1") != "1":
            raise HTTPException(403, "A regisztrációt az admin kikapcsolta.")
        if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise HTTPException(409, "Ez a felhasználónév már foglalt.")
        cur = conn.execute(
            "INSERT INTO users(username, pw_hash, is_admin, created) VALUES (?,?,?,?)",
            (username, hash_password(password), 1 if first else 0, db.now_iso()),
        )
        row = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return public_user(row)


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username.strip(),)).fetchone()
    if row and verify_password(password, row["pw_hash"]):
        return public_user(row)
    return None


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = db.now_iso()
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions(token, user_id, created, last_seen) VALUES (?,?,?,?)",
            (token, user_id, now, now),
        )
        cutoff = (datetime.now(timezone.utc) - timedelta(days=SESSION_DAYS)).isoformat()
        conn.execute("DELETE FROM sessions WHERE last_seen < ?", (cutoff,))
    return token


def delete_session(token: str) -> None:
    with db.get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))


def user_from_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT u.*, s.last_seen FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?",
            (token,),
        ).fetchone()
        if not row:
            return None
        # last_seen frissítése legfeljebb óránként (kevesebb írás az SD kártyára)
        if datetime.fromisoformat(row["last_seen"]) < datetime.now(timezone.utc) - timedelta(hours=1):
            conn.execute("UPDATE sessions SET last_seen=? WHERE token=?", (db.now_iso(), token))
    return public_user(row)


def current_user(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Bejelentkezés szükséges.")
    return user


def require_admin(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if not user["is_admin"]:
        raise HTTPException(403, "Ehhez admin jogosultság kell.")
    return user
