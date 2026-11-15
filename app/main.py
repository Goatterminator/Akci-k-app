"""Akciók app – FastAPI szerver.

Indítás:  python -m app.main     (vagy: uvicorn app.main:app --host 0.0.0.0 --port 8080)
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, db
from .categories import CATEGORIES, CATEGORY_KEYS, STORES, normalize
from .scrapers import SCRAPERS, SCRAPERS_BY_NAME
from .services import gemini, notify, refresh, search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("akciok")

_bg_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    if config.AUTO_REFRESH:
        _spawn(refresh.scheduler_loop())
    yield
    for t in list(_bg_tasks):
        t.cancel()


app = FastAPI(title="Akciók", lifespan=lifespan)


def _split(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


# ------------------------------------------------------------------ meta
@app.get("/api/meta")
def meta() -> dict[str, Any]:
    with db.get_conn() as conn:
        counts = {
            r["store"]: r["n"]
            for r in conn.execute(
                "SELECT store, COUNT(*) n FROM items WHERE active=1 AND kind!='normal' GROUP BY store"
            )
        }
        cat_counts = {
            r["category"]: r["n"]
            for r in conn.execute(
                "SELECT category, COUNT(*) n FROM items WHERE active=1 AND kind='deal' GROUP BY category"
            )
        }
        unseen = conn.execute("SELECT COUNT(*) FROM alerts WHERE seen=0").fetchone()[0]
    settings = db.get_settings()
    return {
        "categories": [{**c, "count": cat_counts.get(c["key"], 0)} for c in CATEGORIES],
        "stores": [{"name": n, **m, "count": counts.get(n, 0)} for n, m in STORES.items()],
        "ai_enabled": gemini.has_key(settings),
        "unseen_alerts": unseen,
        "refresh": refresh.STATE,
    }


# ------------------------------------------------------------------ akciók
@app.get("/api/deals")
def deals(
    q: str = "",
    category: str = "",
    exclude: str = "",
    stores: str = "",
    kinds: str = "deal",
    min_discount: float | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    sort: str = "discount",
    favorites: bool = False,
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return search.list_deals(
        q=q, category=category, exclude_categories=_split(exclude), stores=_split(stores), kinds=_split(kinds) or ["deal"],
        min_discount=min_discount, min_price=min_price, max_price=max_price, sort=sort,
        favorites_only=favorites, limit=limit, offset=offset,
    )


@app.get("/api/items/{item_id:path}")
def item_detail(item_id: str) -> dict[str, Any]:
    item = search.get_item(item_id)
    if not item:
        raise HTTPException(404, "Nincs ilyen tétel")
    return item


@app.get("/api/games")
def games() -> dict[str, Any]:
    free_now = search.list_deals(kinds=["free_game"], sort="ending", limit=50)["items"]
    upcoming = search.list_deals(kinds=["upcoming_free"], limit=50)["items"]
    upcoming.sort(key=lambda i: i.get("valid_from") or "")
    steam = search.list_deals(kinds=["deal"], category="jatek", sort="discount", limit=60)["items"]
    return {"free_now": free_now, "upcoming": upcoming, "deals": steam}


@app.get("/api/coupons")
def coupons() -> dict[str, Any]:
    items = search.list_deals(kinds=["coupon"], sort="price", limit=200)["items"]
    grouped: dict[str, list] = {}
    for it in items:
        grouped.setdefault(it["store"], []).append(it)
    return {"stores": grouped}


# ------------------------------------------------------------------ AI
class AiSearchBody(BaseModel):
    query: str = Field(..., min_length=2, max_length=300)
    category: str = ""
    min_price: float | None = None
    max_price: float | None = None
    stores: list[str] = []
    only_deals: bool = False


@app.post("/api/ai/search")
async def ai_search(body: AiSearchBody) -> dict[str, Any]:
    settings = db.get_settings()
    category = body.category if body.category in CATEGORY_KEYS else ""
    t0 = time.monotonic()
    if not gemini.has_key(settings):
        res = search.keyword_candidates(
            normalize(body.query).split(), category=category, min_price=body.min_price,
            max_price=body.max_price, stores=body.stores, include_normal=not body.only_deals, limit=30,
        )
        return {
            "ai": False,
            "summary": "Nincs Gemini kulcs megadva, ezért egyszerű kulcsszavas keresést végeztem. "
                       "A Beállításokban add meg az ingyenes kulcsot az AI kereséshez.",
            "results": [{"item": it, "reason": None} for it in res],
        }
    try:
        plan = await gemini.interpret_query(settings, body.query)
        keywords = plan.get("keywords") or normalize(body.query).split()
        cat = category or (plan.get("category") or "")
        max_price = body.max_price if body.max_price is not None else plan.get("max_price")
        min_price = body.min_price if body.min_price is not None else plan.get("min_price")
        candidates = await asyncio.to_thread(
            search.keyword_candidates, keywords, category=cat, min_price=min_price,
            max_price=max_price, stores=body.stores, include_normal=not body.only_deals, limit=120,
        )
        if not candidates and cat and not category:
            # a modell által tippelt kategória túl szűk lehetett
            candidates = await asyncio.to_thread(
                search.keyword_candidates, keywords, min_price=min_price, max_price=max_price,
                stores=body.stores, include_normal=not body.only_deals, limit=120,
            )
        if not candidates:
            return {
                "ai": True, "keywords": keywords,
                "summary": "Most nem találtam ilyen terméket az aktuális ajánlatok között. "
                           "Próbáld meg más szavakkal, vagy állíts be figyelőt rá!",
                "results": [],
            }
        ranked = await gemini.rank_candidates(settings, body.query, candidates)
    except gemini.GeminiError as exc:
        raise HTTPException(502, str(exc)) from exc
    by_id = {c["id"]: c for c in candidates}
    with db.get_conn() as conn:
        favs = {r[0] for r in conn.execute("SELECT item_id FROM favorites")}
    results = []
    for p in ranked.get("picks") or []:
        it = by_id[p["id"]]
        it["favorite"] = it["id"] in favs
        results.append({"item": it, "reason": p.get("reason")})
    return {
        "ai": True,
        "keywords": keywords,
        "summary": ranked.get("summary") or "",
        "results": results,
        "considered": len(candidates),
        "seconds": round(time.monotonic() - t0, 1),
    }


@app.post("/api/ai/test")
async def ai_test() -> dict[str, Any]:
    settings = db.get_settings()
    try:
        text = await gemini.generate(settings, [{"text": "Válaszolj egy szóval: működik?"}])
    except gemini.GeminiError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": f"A Gemini válaszolt: {str(text).strip()[:80]}"}


# ------------------------------------------------------------------ bevásárlólista
class ShoppingBody(BaseModel):
    lines: list[str] = Field(..., max_length=60)
    use_ai: bool = True


@app.post("/api/shopping")
async def shopping(body: ShoppingBody) -> dict[str, Any]:
    lines = [l.strip() for l in body.lines if l.strip()][:60]
    if not lines:
        raise HTTPException(400, "Üres lista")
    settings = db.get_settings()
    allowed = None
    ai_note = None
    if body.use_ai and gemini.has_key(settings):
        cands = [await asyncio.to_thread(search.shopping_candidates, l, 25) for l in lines]
        try:
            allowed = await gemini.filter_shopping_candidates(settings, lines, cands)
        except gemini.GeminiError as exc:
            ai_note = f"AI pontosítás kimaradt: {exc}"
    plan = await asyncio.to_thread(search.build_shopping_plan, lines, allowed)
    plan["ai_used"] = allowed is not None
    plan["note"] = ai_note
    return plan


# ------------------------------------------------------------------ kedvencek
@app.get("/api/favorites")
def favorites_list() -> dict[str, Any]:
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT f.item_id, f.added, i.* FROM favorites f LEFT JOIN items i ON i.id=f.item_id "
            "ORDER BY f.added DESC"
        ).fetchall()
    items = []
    for r in rows:
        if r["id"] is None:
            continue
        it = db.row_to_dict(r)
        it["favorite"] = True
        items.append(it)
    return {"items": items}


@app.post("/api/favorites/{item_id:path}")
def favorite_add(item_id: str) -> dict[str, bool]:
    with db.get_conn() as conn:
        if not conn.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone():
            raise HTTPException(404, "Nincs ilyen tétel")
        conn.execute("INSERT OR IGNORE INTO favorites(item_id, added) VALUES (?,?)", (item_id, db.now_iso()))
    return {"ok": True}


@app.delete("/api/favorites/{item_id:path}")
def favorite_remove(item_id: str) -> dict[str, bool]:
    with db.get_conn() as conn:
        conn.execute("DELETE FROM favorites WHERE item_id=?", (item_id,))
    return {"ok": True}


# ------------------------------------------------------------------ figyelők / riasztások
class WatchBody(BaseModel):
    query: str = Field(..., min_length=2, max_length=100)
    max_price: float | None = None
    min_discount: float | None = None
    category: str = ""


@app.get("/api/watches")
def watches_list() -> dict[str, Any]:
    with db.get_conn() as conn:
        watches = [dict(r) for r in conn.execute("SELECT * FROM watches ORDER BY created DESC")]
        alerts = [
            {**db.row_to_dict(r), "alert_id": r["alert_id"], "alert_created": r["alert_created"],
             "seen": r["seen"], "watch_query": r["watch_query"]}
            for r in conn.execute(
                "SELECT i.*, a.id alert_id, a.created alert_created, a.seen, w.query watch_query "
                "FROM alerts a JOIN items i ON i.id=a.item_id JOIN watches w ON w.id=a.watch_id "
                "ORDER BY a.created DESC LIMIT 100"
            )
        ]
    return {"watches": watches, "alerts": alerts}


@app.post("/api/watches")
async def watch_add(body: WatchBody) -> dict[str, Any]:
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO watches(query, max_price, min_discount, category, created) VALUES (?,?,?,?,?)",
            (body.query.strip(), body.max_price, body.min_discount,
             body.category if body.category in CATEGORY_KEYS else None, db.now_iso()),
        )
        watch_id = cur.lastrowid
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM items WHERE active=1 AND kind IN ('deal','coupon','free_game')"
        )]
    # a már most is elérhető találatokat is jelezzük (push nélkül)
    found = await asyncio.to_thread(refresh.check_watches, ids)
    return {"id": watch_id, "matches_now": sum(1 for a in found if a["watch"]["id"] == watch_id)}


@app.delete("/api/watches/{watch_id}")
def watch_remove(watch_id: int) -> dict[str, bool]:
    with db.get_conn() as conn:
        conn.execute("DELETE FROM alerts WHERE watch_id=?", (watch_id,))
        conn.execute("DELETE FROM watches WHERE id=?", (watch_id,))
    return {"ok": True}


@app.post("/api/alerts/seen")
def alerts_seen() -> dict[str, bool]:
    with db.get_conn() as conn:
        conn.execute("UPDATE alerts SET seen=1 WHERE seen=0")
    return {"ok": True}


# ------------------------------------------------------------------ saját (kézi) akciók
class ManualBody(BaseModel):
    store: str = Field(..., min_length=1, max_length=60)
    title: str = Field(..., min_length=2, max_length=200)
    price: float | None = None
    old_price: float | None = None
    category: str = "egyeb"
    url: str | None = None
    image: str | None = None
    valid_to: str | None = None  # YYYY-MM-DD
    description: str | None = None


@app.post("/api/manual")
def manual_add(body: ManualBody) -> dict[str, Any]:
    from .scrapers.base import Deal

    deal = Deal(
        id=f"manual:{body.store}:{uuid.uuid4().hex[:10]}",
        source="manual",
        store=body.store.strip(),
        title=body.title.strip(),
        category=body.category if body.category in CATEGORY_KEYS else "egyeb",
        kind="deal" if body.old_price else "coupon",
        price=body.price,
        old_price=body.old_price,
        url=body.url or None,
        image=body.image or None,
        valid_to=f"{body.valid_to}T23:59:59+01:00" if body.valid_to else None,
        badge="Saját",
        description=body.description,
    ).finalize()
    if deal.kind == "normal":
        deal.kind = "coupon"
    # Nem a refresh.store_deals-t használjuk, mert az inaktiválná a többi kézi tételt.
    _insert_manual(deal)
    return {"id": deal.id}


def _insert_manual(deal) -> None:
    now = db.now_iso()
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO items (id, source, store, title, title_norm, category, kind, price, old_price, "
            "discount_pct, price_huf, old_price_huf, currency, image, url, valid_to, badge, description, "
            "first_seen, last_seen, active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
            (deal.id, "manual", deal.store, deal.title, normalize(deal.title), deal.category, deal.kind,
             deal.price, deal.old_price, deal.discount_pct, deal.price, deal.old_price, "HUF",
             deal.image, deal.url, refresh.norm_dt(deal.valid_to), deal.badge, deal.description, now, now),
        )


@app.delete("/api/manual/{item_id:path}")
def manual_remove(item_id: str) -> dict[str, bool]:
    if not item_id.startswith("manual:"):
        raise HTTPException(400, "Csak saját tétel törölhető")
    with db.get_conn() as conn:
        conn.execute("DELETE FROM items WHERE id=?", (item_id,))
        conn.execute("DELETE FROM favorites WHERE item_id=?", (item_id,))
    return {"ok": True}


# ------------------------------------------------------------------ frissítés / források
@app.get("/api/sources")
def sources() -> dict[str, Any]:
    with db.get_conn() as conn:
        status = {r["name"]: dict(r) for r in conn.execute("SELECT * FROM sources")}
    enabled = set(refresh.enabled_sources())
    return {
        "sources": [
            {
                "name": s.name, "label": s.label, "stores": s.stores, "description": s.description,
                "experimental": s.experimental, "enabled": s.name in enabled, **status.get(s.name, {}),
            }
            for s in SCRAPERS
        ],
        "refresh": refresh.STATE,
    }


@app.post("/api/refresh")
async def refresh_now(source: str = "") -> dict[str, Any]:
    if refresh.STATE["running"]:
        return {"started": False, "message": "Már fut egy frissítés."}
    names = [source] if source in SCRAPERS_BY_NAME else None
    _spawn(refresh.refresh(names))
    return {"started": True}


# ------------------------------------------------------------------ beállítások
SETTING_KEYS = {
    "gemini_api_key", "gemini_model", "refresh_hours", "eur_huf", "ntfy_server",
    "ntfy_topic", "disabled_sources", "emag_urls",
}


def _mask(key: str) -> str:
    return ("•" * 8 + key[-4:]) if key else ""


@app.get("/api/settings")
def settings_get() -> dict[str, Any]:
    s = db.get_settings()
    out = {k: s.get(k, "") for k in SETTING_KEYS}
    out["gemini_api_key"] = _mask(s.get("gemini_api_key", ""))
    return out


@app.put("/api/settings")
def settings_put(values: dict[str, Any]) -> dict[str, Any]:
    clean = {k: v for k, v in values.items() if k in SETTING_KEYS}
    key = str(clean.get("gemini_api_key", "") or "")
    if "gemini_api_key" in clean and key.startswith("•"):
        clean.pop("gemini_api_key")  # nem módosította a maszkolt értéket
    if "refresh_hours" in clean:
        try:
            clean["refresh_hours"] = str(max(1.0, min(48.0, float(clean["refresh_hours"]))))
        except ValueError:
            clean.pop("refresh_hours")
    if "eur_huf" in clean:
        try:
            clean["eur_huf"] = str(float(clean["eur_huf"]))
        except ValueError:
            clean.pop("eur_huf")
    db.set_settings(clean)
    return settings_get()


@app.post("/api/notify/test")
async def notify_test() -> dict[str, Any]:
    ok = await notify.send(db.get_settings(), "Akciók app", "Teszt értesítés – működik! 🎉")
    return {"ok": ok}


# ------------------------------------------------------------------ statikus frontend
@app.exception_handler(404)
async def not_found(request, exc):  # SPA: ismeretlen nem-API útvonal -> index.html
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": getattr(exc, "detail", "Nem található")}, status_code=404)
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/sw.js", include_in_schema=False)
def service_worker() -> FileResponse:
    return FileResponse(config.STATIC_DIR / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    run()
