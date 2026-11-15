"""Akciók app – FastAPI szerver.

Indítás:  python -m app.main     (vagy: uvicorn app.main:app --host 0.0.0.0 --port 8090)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth, config, db
from .auth import current_user, require_admin
from .categories import CATEGORIES, CATEGORY_KEYS, STORES, normalize
from .scrapers import SCRAPERS, SCRAPERS_BY_NAME
from .scrapers.base import Deal
from .services import gemini, notify, refresh, search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("akciok")

_bg_tasks: set[asyncio.Task] = set()

User = dict[str, Any]


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


app = FastAPI(title="Akciók", lifespan=lifespan, docs_url=None, redoc_url=None)

# Ezek az API útvonalak bejelentkezés nélkül is elérhetők
PUBLIC_API = {"/api/auth/state", "/api/auth/login", "/api/auth/register"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    request.state.user = None
    if path.startswith("/api/"):
        request.state.user = await asyncio.to_thread(
            auth.user_from_token, request.cookies.get(auth.COOKIE)
        )
        if request.state.user is None and path not in PUBLIC_API:
            return JSONResponse({"detail": "Bejelentkezés szükséges."}, status_code=401)
    return await call_next(request)


def _split(value: Optional[str]) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


# ------------------------------------------------------------------ auth
class Credentials(BaseModel):
    username: str = Field(..., min_length=2, max_length=40, pattern=r"^[\w.\-@ áéíóöőúüűÁÉÍÓÖŐÚÜŰ]+$")
    password: str = Field(..., min_length=6, max_length=200)


def _set_session(request: Request, response: Response, user_id: int) -> None:
    token = auth.create_session(user_id)
    response.set_cookie(
        auth.COOKIE, token, max_age=auth.SESSION_DAYS * 86400, httponly=True, samesite="lax",
        # HTTPS esetén (pl. `tailscale serve`) a süti csak titkosított kapcsolaton megy
        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
    )


@app.get("/api/auth/state")
def auth_state(request: Request) -> dict[str, Any]:
    return {
        "needs_setup": auth.user_count() == 0,
        "allow_registration": db.get_setting("allow_registration", "1") == "1",
        "user": request.state.user,
    }


@app.post("/api/auth/register")
async def register(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
    user = await asyncio.to_thread(auth.create_user, body.username, body.password)
    _set_session(request, response, user["id"])
    return {"user": user}


@app.post("/api/auth/login")
async def login(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
    user = await asyncio.to_thread(auth.authenticate, body.username, body.password)
    if not user:
        await asyncio.sleep(0.8)  # lassítja a jelszópróbálgatást
        raise HTTPException(401, "Hibás felhasználónév vagy jelszó.")
    _set_session(request, response, user["id"])
    return {"user": user}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    token = request.cookies.get(auth.COOKIE)
    if token:
        auth.delete_session(token)
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


class ProfileBody(BaseModel):
    ntfy_topic: Optional[str] = Field(None, max_length=120)
    current_password: Optional[str] = None
    new_password: Optional[str] = Field(None, min_length=6, max_length=200)


@app.put("/api/me")
def update_me(body: ProfileBody, user: User = Depends(current_user)) -> dict[str, Any]:
    with db.get_conn() as conn:
        if body.ntfy_topic is not None:
            conn.execute("UPDATE users SET ntfy_topic=? WHERE id=?", (body.ntfy_topic.strip(), user["id"]))
        if body.new_password:
            row = conn.execute("SELECT pw_hash FROM users WHERE id=?", (user["id"],)).fetchone()
            if not auth.verify_password(body.current_password or "", row["pw_hash"]):
                raise HTTPException(400, "A jelenlegi jelszó nem megfelelő.")
            conn.execute("UPDATE users SET pw_hash=? WHERE id=?", (auth.hash_password(body.new_password), user["id"]))
        row = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    return {"user": auth.public_user(row)}


@app.post("/api/me/notify-test")
async def notify_test(user: User = Depends(current_user)) -> dict[str, Any]:
    settings = {**db.get_settings(), "ntfy_topic": user["ntfy_topic"]}
    ok = await notify.send(settings, "Akciók app", "Teszt értesítés – működik! 🎉")
    return {"ok": ok}


# ------------------------------------------------------------------ admin: felhasználók
@app.get("/api/admin/users")
def admin_users(_: User = Depends(require_admin)) -> dict[str, Any]:
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    return {"users": [auth.public_user(r) for r in rows]}


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, admin: User = Depends(require_admin)) -> dict[str, bool]:
    if user_id == admin["id"]:
        raise HTTPException(400, "Saját magadat nem törölheted.")
    with db.get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    return {"ok": True}


# ------------------------------------------------------------------ meta
@app.get("/api/meta")
def meta(user: User = Depends(current_user)) -> dict[str, Any]:
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
        unseen = conn.execute(
            "SELECT COUNT(*) FROM alerts a JOIN watches w ON w.id=a.watch_id WHERE a.seen=0 AND w.user_id=?",
            (user["id"],),
        ).fetchone()[0]
        last_ok = conn.execute("SELECT MAX(last_ok) FROM sources").fetchone()[0]
    return {
        "user": user,
        "categories": [{**c, "count": cat_counts.get(c["key"], 0)} for c in CATEGORIES],
        "stores": [{"name": n, **m, "count": counts.get(n, 0)} for n, m in STORES.items()],
        "ai_enabled": gemini.has_key(db.get_settings()),
        "unseen_alerts": unseen,
        "refresh": refresh.STATE,
        "last_refresh": last_ok,
    }


# ------------------------------------------------------------------ akciók
@app.get("/api/deals")
def deals(
    q: str = "",
    category: str = "",
    exclude: str = "",
    stores: str = "",
    kinds: str = "deal",
    min_discount: Optional[float] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort: str = "mix",
    favorites: bool = False,
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    return search.list_deals(
        q=q, category=category, exclude_categories=_split(exclude), stores=_split(stores),
        kinds=_split(kinds) or ["deal"], min_discount=min_discount, min_price=min_price,
        max_price=max_price, sort=sort, favorites_only=favorites, user_id=user["id"],
        limit=limit, offset=offset,
    )


@app.get("/api/items/{item_id:path}")
def item_detail(item_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
    item = search.get_item(item_id, user["id"])
    if not item:
        raise HTTPException(404, "Nincs ilyen tétel")
    return item


@app.get("/api/games")
def games(user: User = Depends(current_user)) -> dict[str, Any]:
    uid = user["id"]
    free_now = search.list_deals(kinds=["free_game"], sort="ending", limit=50, user_id=uid)["items"]
    upcoming = search.list_deals(kinds=["upcoming_free"], limit=50, user_id=uid)["items"]
    upcoming.sort(key=lambda i: i.get("valid_from") or "")
    steam = search.list_deals(kinds=["deal"], category="jatek", sort="discount", limit=60, user_id=uid)["items"]
    return {"free_now": free_now, "upcoming": upcoming, "deals": steam}


@app.get("/api/coupons")
def coupons(user: User = Depends(current_user)) -> dict[str, Any]:
    items = search.list_deals(kinds=["coupon"], sort="price", limit=200, user_id=user["id"])["items"]
    grouped: dict[str, list] = {}
    for it in items:
        grouped.setdefault(it["store"], []).append(it)
    return {"stores": grouped}


# ------------------------------------------------------------------ AI
class AiSearchBody(BaseModel):
    query: str = Field(..., min_length=2, max_length=300)
    category: str = ""
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    stores: list[str] = []
    only_deals: bool = False


def _mark_favorites(items: list[dict[str, Any]], user_id: int) -> None:
    with db.get_conn() as conn:
        favs = {r[0] for r in conn.execute("SELECT item_id FROM favorites WHERE user_id=?", (user_id,))}
    for it in items:
        it["favorite"] = it["id"] in favs


@app.post("/api/ai/search")
async def ai_search(body: AiSearchBody, user: User = Depends(current_user)) -> dict[str, Any]:
    settings = db.get_settings()
    category = body.category if body.category in CATEGORY_KEYS else ""
    t0 = time.monotonic()
    if not gemini.has_key(settings):
        res = search.keyword_candidates(
            normalize(body.query).split(), category=category, min_price=body.min_price,
            max_price=body.max_price, stores=body.stores, include_normal=not body.only_deals, limit=30,
        )
        _mark_favorites(res, user["id"])
        return {
            "ai": False,
            "summary": "Az admin még nem adott meg Gemini kulcsot, ezért egyszerű kulcsszavas "
                       "keresést végeztem.",
            "results": [{"item": it, "reason": None} for it in res],
        }
    try:
        plan = await gemini.interpret_query(settings, body.query)
        keywords = plan.get("keywords") or normalize(body.query).split()
        cat = category or (plan.get("category") or "")
        max_price = body.max_price if body.max_price is not None else plan.get("max_price")
        min_price = body.min_price if body.min_price is not None else plan.get("min_price")
        kwargs = dict(min_price=min_price, max_price=max_price, stores=body.stores,
                      include_normal=not body.only_deals, limit=120)
        candidates = await asyncio.to_thread(search.keyword_candidates, keywords, category=cat, **kwargs)
        if not candidates and cat and not category:
            # a modell által tippelt kategória túl szűk lehetett
            candidates = await asyncio.to_thread(search.keyword_candidates, keywords, **kwargs)
        if not candidates:
            return {
                "ai": True, "keywords": keywords, "results": [],
                "summary": "Most nem találtam ilyen terméket az aktuális ajánlatok között. "
                           "Próbáld meg más szavakkal, vagy állíts be figyelőt rá!",
            }
        ranked = await gemini.rank_candidates(settings, body.query, candidates)
    except gemini.GeminiError as exc:
        raise HTTPException(502, str(exc)) from exc
    by_id = {c["id"]: c for c in candidates}
    picks = [(by_id[p["id"]], p.get("reason")) for p in ranked.get("picks") or []]
    _mark_favorites([it for it, _ in picks], user["id"])
    return {
        "ai": True,
        "keywords": keywords,
        "summary": ranked.get("summary") or "",
        "results": [{"item": it, "reason": reason} for it, reason in picks],
        "considered": len(candidates),
        "seconds": round(time.monotonic() - t0, 1),
    }


# ------------------------------------------------------------------ bevásárlólista
class ShoppingBody(BaseModel):
    lines: list[str] = Field(..., max_length=60)
    use_ai: bool = True


@app.post("/api/shopping")
async def shopping(body: ShoppingBody, _: User = Depends(current_user)) -> dict[str, Any]:
    lines = [line.strip() for line in body.lines if line.strip()][:60]
    if not lines:
        raise HTTPException(400, "Üres lista")
    settings = db.get_settings()
    allowed = None
    ai_note = None
    if body.use_ai and gemini.has_key(settings):
        cands = [await asyncio.to_thread(search.shopping_candidates, line, 25) for line in lines]
        try:
            allowed = await gemini.filter_shopping_candidates(settings, lines, cands)
        except gemini.GeminiError as exc:
            ai_note = f"AI pontosítás kimaradt: {exc}"
    plan = await asyncio.to_thread(search.build_shopping_plan, lines, allowed)
    plan["ai_used"] = allowed is not None
    plan["note"] = ai_note
    return plan


# ------------------------------------------------------------------ kedvencek (felhasználónként)
@app.get("/api/favorites")
def favorites_list(user: User = Depends(current_user)) -> dict[str, Any]:
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT i.* FROM favorites f JOIN items i ON i.id=f.item_id WHERE f.user_id=? "
            "ORDER BY f.added DESC",
            (user["id"],),
        ).fetchall()
    items = [db.row_to_dict(r) for r in rows]
    for it in items:
        it["favorite"] = True
    return {"items": items}


@app.post("/api/favorites/{item_id:path}")
def favorite_add(item_id: str, user: User = Depends(current_user)) -> dict[str, bool]:
    with db.get_conn() as conn:
        if not conn.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone():
            raise HTTPException(404, "Nincs ilyen tétel")
        conn.execute(
            "INSERT OR IGNORE INTO favorites(user_id, item_id, added) VALUES (?,?,?)",
            (user["id"], item_id, db.now_iso()),
        )
    return {"ok": True}


@app.delete("/api/favorites/{item_id:path}")
def favorite_remove(item_id: str, user: User = Depends(current_user)) -> dict[str, bool]:
    with db.get_conn() as conn:
        conn.execute("DELETE FROM favorites WHERE item_id=? AND user_id=?", (item_id, user["id"]))
    return {"ok": True}


# ------------------------------------------------------------------ figyelők / riasztások
class WatchBody(BaseModel):
    query: str = Field(..., min_length=2, max_length=100)
    max_price: Optional[float] = None
    min_discount: Optional[float] = None
    category: str = ""


@app.get("/api/watches")
def watches_list(user: User = Depends(current_user)) -> dict[str, Any]:
    with db.get_conn() as conn:
        watches = [dict(r) for r in conn.execute(
            "SELECT * FROM watches WHERE user_id=? ORDER BY created DESC", (user["id"],)
        )]
        alerts = [
            {**db.row_to_dict(r), "alert_id": r["alert_id"], "seen": r["seen"], "watch_query": r["watch_query"]}
            for r in conn.execute(
                "SELECT i.*, a.id alert_id, a.seen, w.query watch_query "
                "FROM alerts a JOIN items i ON i.id=a.item_id JOIN watches w ON w.id=a.watch_id "
                "WHERE w.user_id=? ORDER BY a.created DESC LIMIT 100",
                (user["id"],),
            )
        ]
    _mark_favorites(alerts, user["id"])
    return {"watches": watches, "alerts": alerts}


@app.post("/api/watches")
async def watch_add(body: WatchBody, user: User = Depends(current_user)) -> dict[str, Any]:
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO watches(user_id, query, max_price, min_discount, category, created) "
            "VALUES (?,?,?,?,?,?)",
            (user["id"], body.query.strip(), body.max_price, body.min_discount,
             body.category if body.category in CATEGORY_KEYS else None, db.now_iso()),
        )
        watch_id = cur.lastrowid
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM items WHERE active=1 AND kind IN ('deal','coupon','free_game')"
        )]
    # a már most is elérhető találatokat is felvesszük (push értesítés nélkül)
    found = await asyncio.to_thread(refresh.check_watches, ids)
    return {"id": watch_id, "matches_now": sum(1 for a in found if a["watch"]["id"] == watch_id)}


@app.delete("/api/watches/{watch_id}")
def watch_remove(watch_id: int, user: User = Depends(current_user)) -> dict[str, bool]:
    with db.get_conn() as conn:
        conn.execute("DELETE FROM watches WHERE id=? AND user_id=?", (watch_id, user["id"]))
    return {"ok": True}


@app.post("/api/alerts/seen")
def alerts_seen(user: User = Depends(current_user)) -> dict[str, bool]:
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE alerts SET seen=1 WHERE seen=0 AND watch_id IN (SELECT id FROM watches WHERE user_id=?)",
            (user["id"],),
        )
    return {"ok": True}


# ------------------------------------------------------------------ saját (kézi) akciók
class ManualBody(BaseModel):
    store: str = Field(..., min_length=1, max_length=60)
    title: str = Field(..., min_length=2, max_length=200)
    price: Optional[float] = None
    old_price: Optional[float] = None
    category: str = "egyeb"
    url: Optional[str] = Field(None, max_length=500)
    valid_to: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    description: Optional[str] = Field(None, max_length=500)


@app.post("/api/manual")
def manual_add(body: ManualBody, user: User = Depends(current_user)) -> dict[str, Any]:
    if body.url and not body.url.startswith(("http://", "https://")):
        raise HTTPException(400, "A link http:// vagy https:// kezdetű legyen.")
    deal = Deal(
        id=f"manual:{body.store.strip()}:{uuid.uuid4().hex[:10]}",
        source="manual",
        store=body.store.strip(),
        title=body.title.strip(),
        category=body.category if body.category in CATEGORY_KEYS else "egyeb",
        kind="deal" if body.old_price else "coupon",
        price=body.price,
        old_price=body.old_price,
        url=body.url or None,
        valid_to=f"{body.valid_to}T23:59:59+01:00" if body.valid_to else None,
        badge="Saját",
        description=body.description,
        extra={"added_by": user["id"], "added_by_name": user["username"]},
    ).finalize()
    if deal.kind == "normal":
        deal.kind = "coupon"
    # Nem a refresh.store_deals-t használjuk, mert az inaktiválná a többi kézi tételt.
    now = db.now_iso()
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO items (id, source, store, title, title_norm, category, kind, price, old_price, "
            "discount_pct, price_huf, old_price_huf, currency, url, valid_to, badge, description, extra, "
            "first_seen, last_seen, active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
            (deal.id, "manual", deal.store, deal.title, normalize(deal.title), deal.category, deal.kind,
             deal.price, deal.old_price, deal.discount_pct, deal.price, deal.old_price, "HUF",
             deal.url, refresh.norm_dt(deal.valid_to), deal.badge, deal.description,
             json.dumps(deal.extra, ensure_ascii=False), now, now),
        )
    return {"id": deal.id}


@app.delete("/api/manual/{item_id:path}")
def manual_remove(item_id: str, user: User = Depends(current_user)) -> dict[str, bool]:
    if not item_id.startswith("manual:"):
        raise HTTPException(400, "Csak saját tétel törölhető")
    item = search.get_item(item_id, user["id"])
    if not item:
        raise HTTPException(404, "Nincs ilyen tétel")
    if not user["is_admin"] and (item.get("extra") or {}).get("added_by") != user["id"]:
        raise HTTPException(403, "Csak a saját tételedet (vagy adminként bármelyiket) törölheted.")
    with db.get_conn() as conn:
        conn.execute("DELETE FROM items WHERE id=?", (item_id,))
        conn.execute("DELETE FROM favorites WHERE item_id=?", (item_id,))
    return {"ok": True}


# ------------------------------------------------------------------ admin: frissítés / források
@app.get("/api/sources")
def sources(_: User = Depends(require_admin)) -> dict[str, Any]:
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
async def refresh_now(source: str = "", _: User = Depends(require_admin)) -> dict[str, Any]:
    if refresh.STATE["running"]:
        return {"started": False, "message": "Már fut egy frissítés."}
    names = [source] if source in SCRAPERS_BY_NAME else None
    _spawn(refresh.refresh(names))
    return {"started": True}


# ------------------------------------------------------------------ admin: beállítások
SETTING_KEYS = {
    "gemini_api_key", "gemini_model", "refresh_hours", "eur_huf", "ntfy_server",
    "disabled_sources", "emag_urls", "allow_registration",
}


def _mask(key: str) -> str:
    return ("•" * 8 + key[-4:]) if key else ""


@app.get("/api/settings")
def settings_get(_: User = Depends(require_admin)) -> dict[str, Any]:
    s = db.get_settings()
    out = {k: s.get(k, "") for k in SETTING_KEYS}
    # A teljes API kulcs soha nem megy vissza a böngészőbe
    out["gemini_api_key"] = _mask(s.get("gemini_api_key", ""))
    return out


@app.put("/api/settings")
def settings_put(values: dict[str, Any], admin: User = Depends(require_admin)) -> dict[str, Any]:
    clean = {k: v for k, v in values.items() if k in SETTING_KEYS}
    key = str(clean.get("gemini_api_key", "") or "")
    if "gemini_api_key" in clean and key.startswith("•"):
        clean.pop("gemini_api_key")  # a maszkolt értéket nem írjuk vissza
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
    if "allow_registration" in clean:
        clean["allow_registration"] = "1" if str(clean["allow_registration"]) in ("1", "true", "True") else "0"
    db.set_settings(clean)
    return settings_get(admin)


@app.post("/api/ai/test")
async def ai_test(_: User = Depends(require_admin)) -> dict[str, Any]:
    try:
        text = await gemini.generate(db.get_settings(), [{"text": "Válaszolj egy szóval: működik?"}])
    except gemini.GeminiError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": f"A Gemini válaszolt: {str(text).strip()[:80]}"}


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


def _port_free(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def run() -> None:
    import sys

    import uvicorn

    if not _port_free(config.HOST, config.PORT):
        sys.exit(
            f"\n!! A(z) {config.PORT} port már foglalt (valószínűleg egy másik projekted használja).\n"
            f"   Állíts be másikat a .env fájlban (pl. PORT={config.PORT + 1}), vagy futtasd így:\n"
            f"   PORT={config.PORT + 1} python -m app.main\n"
        )
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, log_level="info",
                proxy_headers=True, forwarded_allow_ips="127.0.0.1")


if __name__ == "__main__":
    run()
