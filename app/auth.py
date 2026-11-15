"""Felhasználók és munkamenetek.

* Az ELSŐ regisztrált felhasználó automatikusan admin: csak ő látja a
  Beállításokat (Gemini API kulcs, források, frissítés, felhasználók).
* Mindenki más sima (nem admin) fiókot kap regisztrációkor. Az admin a
  regisztrációt kikapcsolhatja; alapból legfeljebb 5 sima fiók regisztrálhat.
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


# ------------------------------------------------------------------ próbálgatás elleni védelem
# Felhasználónevenként számoljuk a hibás belépéseket (memóriában). Nyilvános (Funnel) elérésnél
# a botok jelszópróbálgatását lassítja; IP alapján nem számolunk, mert a Tailscale proxy mögött
# minden kérés a 127.0.0.1-ről jöhet, és akkor mindenkit kizárnánk.
MAX_FAILURES = 8
LOCKOUT_SECONDS = 15 * 60
_failures: dict[str, list[float]] = {}


def _recent_failures(username: str, now: float) -> list[float]:
    key = username.strip().lower()
    recent = [t for t in _failures.get(key, []) if now - t < LOCKOUT_SECONDS]
    _failures[key] = recent
    return recent


def check_lockout(username: str) -> None:
    import time

    if len(_recent_failures(username, time.time())) >= MAX_FAILURES:
        raise HTTPException(429, "Túl sok sikertelen próbálkozás. Várj 15 percet, és próbáld újra.")


def record_failure(username: str) -> None:
    import time

    now = time.time()
    _recent_failures(username, now).append(now)
    if len(_failures) > 5000:  # memóriavédelem
        _failures.clear()


def clear_failures(username: str) -> None:
    _failures.pop(username.strip().lower(), None)


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
        try:
            max_reg = int(float(db.get_setting("max_registrations", "5") or 0))
        except ValueError:
            max_reg = 5
        registered = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin=0").fetchone()[0]
        if not first and max_reg and registered >= max_reg:
            raise HTTPException(403, f"Betelt a regisztráció (legfeljebb {max_reg} fiók). Kérd meg az admint.")
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
