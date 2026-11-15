"""Források frissítése, tárolás, árelőzmény, figyelő-riasztások, ütemezés."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from .. import db
from ..categories import normalize
from ..scrapers import SCRAPERS, SCRAPERS_BY_NAME, Deal, ScrapeContext, SourceBlocked, make_client
from ..scrapers.base import eur_rate
from . import gemini, notify

log = logging.getLogger("akciok.refresh")

_lock = asyncio.Lock()
STATE: dict[str, Any] = {"running": False, "current": None, "queue": [], "started": None}


def norm_dt(value: str | None) -> str | None:
    """Különféle ISO formátumok -> egységes UTC ISO string (szövegesen összehasonlítható)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def to_huf(value: float | None, currency: str, eur_huf: float) -> float | None:
    if value is None:
        return None
    if currency == "EUR":
        return round(value * eur_huf)
    return value


# ------------------------------------------------------------------ tárolás
def store_deals(source: str, deals: list[Deal], eur_huf: float) -> list[str]:
    """Upsert; a most nem látott tételek inaktívak lesznek. Visszaadja az "új akció" id-kat."""
    now = db.now_iso()
    day = db.today()
    fresh_deals: list[str] = []
    with db.get_conn() as conn:
        existing = {
            r["id"]: r
            for r in conn.execute(
                "SELECT id, price, old_price, kind, active FROM items WHERE source=?", (source,)
            )
        }
        for d in deals:
            prev = existing.get(d.id)
            price_huf = to_huf(d.price, d.currency, eur_huf)
            old_huf = to_huf(d.old_price, d.currency, eur_huf)
            conn.execute(
                """
                INSERT INTO items (id, source, store, title, title_norm, category, subcategory, kind,
                    price, old_price, discount_pct, price_huf, old_price_huf, currency, unit_price, unit,
                    image, url, valid_from, valid_to, badge, description, product_key, extra,
                    first_seen, last_seen, active)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                ON CONFLICT(id) DO UPDATE SET
                    store=excluded.store, title=excluded.title, title_norm=excluded.title_norm,
                    category=excluded.category, subcategory=excluded.subcategory, kind=excluded.kind,
                    price=excluded.price, old_price=excluded.old_price,
                    discount_pct=excluded.discount_pct, price_huf=excluded.price_huf,
                    old_price_huf=excluded.old_price_huf, currency=excluded.currency,
                    unit_price=excluded.unit_price, unit=excluded.unit, image=excluded.image,
                    url=excluded.url, valid_from=excluded.valid_from, valid_to=excluded.valid_to,
                    badge=excluded.badge, description=excluded.description,
                    product_key=excluded.product_key, extra=excluded.extra,
                    last_seen=excluded.last_seen, active=1
                """,
                (
                    d.id, d.source, d.store, d.title, normalize(d.title), d.category, d.subcategory,
                    d.kind, d.price, d.old_price, d.discount_pct, price_huf, old_huf, d.currency,
                    d.unit_price, d.unit, d.image, d.url, norm_dt(d.valid_from), norm_dt(d.valid_to),
                    d.badge, d.description, d.product_key,
                    json.dumps(d.extra, ensure_ascii=False) if d.extra else None, now, now,
                ),
            )
            changed = prev is None or prev["price"] != d.price or prev["old_price"] != d.old_price
            if d.price is not None and changed:
                conn.execute(
                    "INSERT OR REPLACE INTO price_history(item_id, day, price, old_price) VALUES (?,?,?,?)",
                    (d.id, day, d.price, d.old_price),
                )
            is_deal = d.kind in ("deal", "free_game", "coupon")
            if is_deal and (
                prev is None
                or not prev["active"]
                or prev["kind"] != d.kind
                or (prev["price"] is not None and d.price is not None and d.price < prev["price"])
            ):
                fresh_deals.append(d.id)
        conn.execute(
            "UPDATE items SET active=0 WHERE source=? AND last_seen < ? AND active=1", (source, now)
        )
    return fresh_deals


def record_source(name: str, ok: bool, count: int, error: str | None, duration: float) -> None:
    now = db.now_iso()
    with db.get_conn() as conn:
        conn.execute(
            """
            INSERT INTO sources(name, last_run, last_ok, ok, count, error, duration)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET last_run=excluded.last_run,
                last_ok=COALESCE(excluded.last_ok, sources.last_ok), ok=excluded.ok,
                count=CASE WHEN excluded.ok=1 THEN excluded.count ELSE sources.count END,
                error=excluded.error, duration=excluded.duration
            """,
            (name, now, now if ok else None, 1 if ok else 0, count, error, round(duration, 1)),
        )


# ------------------------------------------------------------------ figyelő
def watch_matches(watch: dict[str, Any], item: dict[str, Any]) -> bool:
    tokens = normalize(watch["query"]).split()
    title = " " + (item.get("title_norm") or normalize(item.get("title"))) + " "
    if not tokens or not all((" " + t) in title for t in tokens):
        return False
    if watch.get("category") and item.get("category") != watch["category"]:
        return False
    if watch.get("max_price") is not None and (item.get("price_huf") or 0) > watch["max_price"]:
        return False
    if watch.get("min_discount") and (item.get("discount_pct") or 0) < watch["min_discount"]:
        return False
    return True


def check_watches(item_ids: list[str]) -> list[dict[str, Any]]:
    if not item_ids:
        return []
    new_alerts: list[dict[str, Any]] = []
    with db.get_conn() as conn:
        watches = [dict(r) for r in conn.execute("SELECT * FROM watches")]
        if not watches:
            return []
        for chunk_start in range(0, len(item_ids), 500):
            chunk = item_ids[chunk_start:chunk_start + 500]
            rows = conn.execute(
                f"SELECT * FROM items WHERE id IN ({','.join('?' * len(chunk))})", chunk
            ).fetchall()
            for row in rows:
                item = dict(row)
                for w in watches:
                    if watch_matches(w, item):
                        cur = conn.execute(
                            "INSERT OR IGNORE INTO alerts(watch_id, item_id, created) VALUES (?,?,?)",
                            (w["id"], item["id"], db.now_iso()),
                        )
                        if cur.rowcount:
                            new_alerts.append({"watch": w, "item": item})
    return new_alerts


# ------------------------------------------------------------------ futtatás
async def run_source(name: str) -> dict[str, Any]:
    scraper = SCRAPERS_BY_NAME[name]
    settings = db.get_settings()
    t0 = time.monotonic()
    async with make_client() as client:
        ctx = ScrapeContext(settings=settings, client=client)
        try:
            deals = await scraper.fetch(ctx)
            if name == "burgerking":
                await gemini.enrich_coupon_prices(deals, settings, client)
        except SourceBlocked as exc:
            record_source(name, False, 0, str(exc), time.monotonic() - t0)
            return {"source": name, "ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - egy forrás hibája ne állítsa le a többit
            log.exception("Forrás hiba: %s", name)
            record_source(name, False, 0, f"{type(exc).__name__}: {exc}", time.monotonic() - t0)
            return {"source": name, "ok": False, "error": str(exc)}

    fresh = await asyncio.to_thread(store_deals, name, deals, eur_rate(settings))
    alerts = await asyncio.to_thread(check_watches, fresh)
    record_source(name, True, len(deals), "; ".join(ctx.log[:5]) or None, time.monotonic() - t0)
    if alerts:
        await notify.send_alerts(alerts, settings)
    log.info("%s: %d tétel, %d új akció, %d riasztás", name, len(deals), len(fresh), len(alerts))
    return {"source": name, "ok": True, "count": len(deals), "new": len(fresh), "alerts": len(alerts)}


def enabled_sources(settings: dict[str, str] | None = None) -> list[str]:
    settings = settings or db.get_settings()
    disabled = {s.strip() for s in (settings.get("disabled_sources") or "").split(",") if s.strip()}
    return [s.name for s in SCRAPERS if s.name not in disabled]


async def refresh(names: list[str] | None = None) -> list[dict[str, Any]]:
    names = names or enabled_sources()
    results = []
    STATE["queue"] = list(names)
    async with _lock:
        STATE["running"] = True
        STATE["started"] = db.now_iso()
        try:
            for name in names:
                STATE["current"] = name
                STATE["queue"] = [n for n in STATE["queue"] if n != name]
                results.append(await run_source(name))
            await asyncio.to_thread(maintenance)
        finally:
            STATE.update(running=False, current=None, queue=[])
    return results


def due_sources() -> list[str]:
    settings = db.get_settings()
    try:
        hours = max(1.0, float(settings.get("refresh_hours") or 6))
    except ValueError:
        hours = 6.0
    with db.get_conn() as conn:
        last = {r["name"]: r["last_run"] for r in conn.execute("SELECT name, last_run FROM sources")}
    due = []
    limit = datetime.now(timezone.utc) - timedelta(hours=hours)
    for name in enabled_sources(settings):
        ts = last.get(name)
        if not ts or datetime.fromisoformat(ts) < limit:
            due.append(name)
    return due


def maintenance() -> None:
    cutoff_hist = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    cutoff_items = (datetime.now(timezone.utc) - timedelta(days=60)).replace(microsecond=0).isoformat()
    with db.get_conn() as conn:
        conn.execute("DELETE FROM price_history WHERE day < ?", (cutoff_hist,))
        conn.execute(
            "DELETE FROM items WHERE active=0 AND last_seen < ? AND source != 'manual' "
            "AND id NOT IN (SELECT item_id FROM favorites)",
            (cutoff_items,),
        )
        conn.execute(
            "DELETE FROM price_history WHERE item_id NOT IN (SELECT id FROM items)"
        )
        conn.execute("DELETE FROM alerts WHERE item_id NOT IN (SELECT id FROM items)")
        conn.execute(
            "DELETE FROM cache WHERE created < ?",
            ((datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),),
        )


async def scheduler_loop() -> None:
    """Ötpercenként megnézi, melyik forrás esedékes, és frissíti."""
    await asyncio.sleep(3)
    while True:
        try:
            if not _lock.locked():
                due = await asyncio.to_thread(due_sources)
                if due:
                    await refresh(due)
        except Exception:  # noqa: BLE001
            log.exception("Ütemező hiba")
        await asyncio.sleep(300)
