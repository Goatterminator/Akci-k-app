"""Napi AI-keret felhasználónként (az admin korlátlan, de őt is számoljuk a statisztikához)."""
from __future__ import annotations

from typing import Any, Optional

from .. import db


def effective_limit(user: dict[str, Any], settings: dict[str, str]) -> Optional[int]:
    """A felhasználó napi AI-kerete; None = korlátlan (admin, vagy 0 a közös beállításban)."""
    if user.get("is_admin"):
        return None
    if user.get("ai_limit") is not None:
        return max(0, int(user["ai_limit"]))  # egyedi keret; 0 = nem használhat AI-t
    try:
        limit = int(float(settings.get("ai_daily_limit") or 0))
    except ValueError:
        limit = 30
    return limit if limit > 0 else None  # közös keret; 0 = korlátlan


def used_today(user_id: int) -> int:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT count FROM ai_usage WHERE user_id=? AND day=?", (user_id, db.today())
        ).fetchone()
    return row["count"] if row else 0


def try_consume(user: dict[str, Any], settings: dict[str, str]) -> tuple[bool, Optional[int]]:
    """Egy AI-hívás elszámolása. (False, limit) ha a napi keret elfogyott."""
    limit = effective_limit(user, settings)
    day = db.today()
    with db.get_conn() as conn:
        row = conn.execute("SELECT count FROM ai_usage WHERE user_id=? AND day=?", (user["id"], day)).fetchone()
        if limit is not None and row and row["count"] >= limit:
            return False, limit
        if limit == 0:
            return False, limit
        conn.execute(
            "INSERT INTO ai_usage(user_id, day, count) VALUES (?,?,1) "
            "ON CONFLICT(user_id, day) DO UPDATE SET count=count+1",
            (user["id"], day),
        )
        conn.execute("DELETE FROM ai_usage WHERE day < date('now', '-30 day')")
    return True, limit
