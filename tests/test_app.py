"""API tesztek: felhasználók/jogosultságok, akciók, figyelők, bevásárlólista."""
from conftest import load

from app.scrapers.arfigyelo import parse_products
from app.scrapers.lidl import parse_items
from app.services import refresh


def seed():
    refresh.store_deals("arfigyelo", parse_products(load("arfigyelo_products.json")["products"], "elelmiszer", "Tészta"), 390)
    refresh.store_deals("lidl", parse_items(load("lidl_search.json")["items"]), 390)


def open_registration(client):
    assert client.put("/api/settings", json={"allow_registration": "1"}).status_code == 200


def register(client, name="admin", pw="titok123"):
    r = client.post("/api/auth/register", json={"username": name, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["user"]


def test_requires_login(client):
    assert client.get("/api/deals").status_code == 401
    assert client.get("/api/auth/state").json()["needs_setup"] is True


def test_first_user_is_admin_and_others_are_not(client):
    admin = register(client, "admin")
    assert admin["is_admin"] is True
    assert client.get("/api/settings").status_code == 200
    # a regisztráció nyitva marad, de a többiek sima fiókot kapnak
    assert client.get("/api/settings").json()["allow_registration"] == "1"

    client.post("/api/auth/logout")
    user = register(client, "bela")
    assert user["is_admin"] is False
    assert client.get("/api/settings").status_code == 403
    assert client.put("/api/settings", json={"gemini_api_key": "x"}).status_code == 403
    assert client.post("/api/refresh").status_code == 403
    assert client.get("/api/admin/users").status_code == 403


def test_api_key_is_never_returned_in_full(client):
    register(client)
    client.put("/api/settings", json={"gemini_api_key": "AIzaSECRET-1234"})
    got = client.get("/api/settings").json()["gemini_api_key"]
    assert "SECRET" not in got and got.endswith("1234")
    # a maszkolt érték visszaküldése nem írja felül a kulcsot
    client.put("/api/settings", json={"gemini_api_key": got})
    from app import db
    assert db.get_setting("gemini_api_key") == "AIzaSECRET-1234"


def test_registration_can_be_disabled(client):
    register(client)
    client.put("/api/settings", json={"allow_registration": "0"})
    client.post("/api/auth/logout")
    r = client.post("/api/auth/register", json={"username": "masik", "password": "jelszo99"})
    assert r.status_code == 403


def test_login_wrong_password(client):
    register(client, "admin", "titok123")
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"username": "admin", "password": "rossz999"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "titok123"}).status_code == 200


def test_deals_feed_and_favorites_are_per_user(client):
    seed()
    register(client, "admin")
    open_registration(client)
    data = client.get("/api/deals?sort=discount").json()
    assert data["total"] > 0
    top = data["items"][0]
    assert top["discount_pct"] == max(i["discount_pct"] for i in data["items"])
    assert client.post(f"/api/favorites/{top['id']}").status_code == 200
    assert len(client.get("/api/favorites").json()["items"]) == 1

    client.post("/api/auth/logout")
    register(client, "bela")
    assert client.get("/api/favorites").json()["items"] == []


def test_mix_sort_and_filters(client):
    seed()
    register(client)
    mix = client.get("/api/deals?sort=mix&limit=10").json()["items"]
    assert {i["store"] for i in mix[:6]} >= {"Lidl"}
    only_lidl = client.get("/api/deals?stores=Lidl").json()["items"]
    assert only_lidl and all(i["store"] == "Lidl" for i in only_lidl)
    cheap = client.get("/api/deals?max_price=200").json()["items"]
    assert all(i["price_huf"] <= 200 for i in cheap)


def test_watch_matches_existing_and_new_deals(client):
    seed()
    register(client)
    r = client.post("/api/watches", json={"query": "kivi"}).json()
    assert r["matches_now"] == 1
    alerts = client.get("/api/watches").json()["alerts"]
    assert alerts and "kivi" in alerts[0]["title"].lower()


def test_price_history_and_price_check(client):
    seed()
    register(client)
    item = client.get("/api/deals?stores=Lidl&sort=discount").json()["items"][0]
    detail = client.get(f"/api/items/{item['id']}").json()
    assert detail["history"] and detail["price_check"]["verdict"] == "unknown"


def test_items_disappear_when_source_drops_them(fresh_db):
    seed()
    from app import db
    refresh.store_deals("lidl", [], 390)
    with db.get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM items WHERE source='lidl' AND active=1").fetchone()[0] == 0


def test_shopping_plan(client):
    seed()
    register(client)
    plan = client.post("/api/shopping", json={"lines": ["kivi", "nemletezotermek"], "use_ai": False}).json()
    assert plan["found"] == 1
    assert plan["lines"][0]["best"]["store"] == "Lidl"
    assert plan["lines"][1]["best"] is None


def test_manual_deal_permissions(client):
    register(client, "admin")
    open_registration(client)
    client.post("/api/auth/logout")
    register(client, "bela")
    item_id = client.post("/api/manual", json={"store": "McDonald's", "title": "2 McChicken", "price": 1490}).json()["id"]
    coupons = client.get("/api/coupons").json()["stores"]
    assert coupons["McDonald's"][0]["title"] == "2 McChicken"
    client.post("/api/auth/logout")
    register(client, "cecil")
    assert client.delete(f"/api/manual/{item_id}").status_code == 403
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "admin", "password": "titok123"})
    assert client.delete(f"/api/manual/{item_id}").status_code == 200


def test_login_lockout_after_many_failures(client):
    from app import auth

    auth._failures.clear()
    register(client, "admin", "titok123")
    client.post("/api/auth/logout")
    for _ in range(auth.MAX_FAILURES):
        assert client.post("/api/auth/login", json={"username": "admin", "password": "rossz999"}).status_code == 401
    # a helyes jelszó is tiltva a zárolás alatt
    assert client.post("/api/auth/login", json={"username": "admin", "password": "titok123"}).status_code == 429
    auth._failures.clear()
    assert client.post("/api/auth/login", json={"username": "admin", "password": "titok123"}).status_code == 200


def test_max_five_registrations_besides_admin(client):
    register(client, "admin")
    assert client.get("/api/settings").json()["max_registrations"] == "5"
    client.post("/api/auth/logout")
    for i in range(5):
        user = register(client, f"user{i}")
        assert user["is_admin"] is False
        client.post("/api/auth/logout")
    r = client.post("/api/auth/register", json={"username": "hatodik", "password": "jelszo99"})
    assert r.status_code == 403 and "Betelt" in r.json()["detail"]


def test_ai_daily_limit_for_regular_users(client, monkeypatch):
    from app.services import gemini

    async def fake_interpret(settings, query):
        return {"keywords": ["kivi"], "category": "", "sort": "discount"}

    async def fake_rank(settings, query, candidates, limit=12):
        return {"summary": "ok", "picks": [{"id": candidates[0]["id"], "reason": "olcsó"}]}

    monkeypatch.setattr(gemini, "interpret_query", fake_interpret)
    monkeypatch.setattr(gemini, "rank_candidates", fake_rank)
    seed()
    register(client, "admin")
    client.put("/api/settings", json={"gemini_api_key": "AIzaTEST", "ai_daily_limit": "2"})
    for _ in range(4):  # az adminra nincs limit
        assert client.post("/api/ai/search", json={"query": "kivi"}).status_code == 200
    client.post("/api/auth/logout")
    register(client, "bela")
    assert client.post("/api/ai/search", json={"query": "kivi"}).json()["results"][0]["reason"] == "olcsó"
    assert client.post("/api/ai/search", json={"query": "kivi"}).status_code == 200
    r = client.post("/api/ai/search", json={"query": "kivi"})
    assert r.status_code == 429 and "napi" in r.json()["detail"]


def test_admin_sees_usage_and_sets_per_user_limit(client, monkeypatch):
    from app.services import gemini

    async def fake_interpret(settings, query):
        return {"keywords": ["kivi"], "category": "", "sort": "discount"}

    async def fake_rank(settings, query, candidates, limit=12):
        return {"summary": "ok", "picks": []}

    monkeypatch.setattr(gemini, "interpret_query", fake_interpret)
    monkeypatch.setattr(gemini, "rank_candidates", fake_rank)
    seed()
    register(client, "admin")
    client.put("/api/settings", json={"gemini_api_key": "AIzaTEST"})
    client.post("/api/auth/logout")
    bela = register(client, "bela")
    for _ in range(3):
        client.post("/api/ai/search", json={"query": "kivi"})
    assert client.get("/api/meta").json()["ai_today"] == 3
    assert client.get("/api/admin/users").status_code == 403

    def login(name):
        client.post("/api/auth/logout")
        assert client.post("/api/auth/login", json={"username": name, "password": "titok123"}).status_code == 200

    def bela_row():
        return {u["username"]: u for u in client.get("/api/admin/users").json()["users"]}["bela"]

    login("admin")
    row = bela_row()
    assert row["ai_today"] == 3 and row["ai_effective_limit"] == 30 and len(row["ai_week"]) == 7
    # egyedi keret: 3 -> bela kifogyott
    assert client.put(f"/api/admin/users/{bela['id']}", json={"ai_limit": 3}).status_code == 200
    login("bela")
    assert client.post("/api/ai/search", json={"query": "kivi"}).status_code == 429
    login("admin")
    # 0 = nem használhat AI-t; null = vissza a közös keretre
    client.put(f"/api/admin/users/{bela['id']}", json={"ai_limit": 0})
    assert bela_row()["ai_effective_limit"] == 0
    client.put(f"/api/admin/users/{bela['id']}", json={"ai_limit": None})
    assert bela_row()["ai_effective_limit"] == 30
    # törlés
    assert client.delete(f"/api/admin/users/{bela['id']}").status_code == 200
    assert "bela" not in {u["username"] for u in client.get("/api/admin/users").json()["users"]}


def test_migration_adds_ai_limit_column(tmp_path, monkeypatch):
    import sqlite3

    from app import config, db

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, "
                 "pw_hash TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0, ntfy_topic TEXT, created TEXT NOT NULL)")
    conn.execute("INSERT INTO users(username, pw_hash, is_admin, created) VALUES ('vince','x',1,'2026-01-01')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(config, "DB_PATH", path)
    db.init_db()
    with db.get_conn() as c:
        assert "ai_limit" in {r[1] for r in c.execute("PRAGMA table_info(users)")}
        assert c.execute("SELECT username FROM users").fetchone()[0] == "vince"


# ------------------------------------------------------------------ AI figyelő
def seed_steam():
    from app.scrapers.games import parse_steam

    refresh.store_deals("steam", parse_steam(load("steam_results.html"), 390), 390)


def fake_ai(monkeypatch, seen_candidates):
    from app.services import gemini

    async def fake_interpret(settings, query):
        return {"keywords": ["jatek"], "category": "jatek", "stores": ["Steam"], "max_price": None, "sort": "discount"}

    async def fake_match(settings, description, candidates, limit=10):
        seen_candidates.extend(candidates)
        return [{"id": candidates[0]["id"], "reason": "jó értékelés, -90%"}]

    monkeypatch.setattr(gemini, "interpret_query", fake_interpret)
    monkeypatch.setattr(gemini, "match_watch", fake_match)


def test_ai_watch_uses_plan_and_ai_decision(client, monkeypatch):
    seen = []
    fake_ai(monkeypatch, seen)
    seed()
    seed_steam()
    register(client, "admin")
    client.put("/api/settings", json={"gemini_api_key": "AIzaTEST"})
    r = client.post("/api/watches", json={"query": "olcsó jó steames játék", "use_ai": True})
    assert r.status_code == 200, r.text
    assert r.json()["matches_now"] == 1 and r.json()["plan"]["stores"] == ["Steam"]
    # az AI csak Steam jelölteket kapott (az élelmiszerek ki lettek szűrve)
    assert seen and all(c["store"] == "Steam" for c in seen)
    data = client.get("/api/watches").json()
    assert data["watches"][0]["use_ai"] == 1 and data["watches"][0]["ai_plan"]["category"] == "jatek"
    assert data["alerts"][0]["reason"] == "jó értékelés, -90%" and data["alerts"][0]["watch_ai"] is True


def test_ai_watch_runs_on_new_deals_and_counts_quota(client, monkeypatch):
    import asyncio

    from app import db
    from app.scrapers.base import Deal

    seen = []
    fake_ai(monkeypatch, seen)
    register(client, "admin")
    client.put("/api/settings", json={"gemini_api_key": "AIzaTEST"})
    client.post("/api/auth/logout")
    bela = register(client, "bela")
    assert client.post("/api/watches", json={"query": "olcsó jó steames játék", "use_ai": True}).status_code == 200
    # új Steam akció érkezik a frissítéskor
    new = [Deal(id="steam:Steam:999", source="steam", store="Steam", title="Új Játék", category="jatek",
                price=1.99, old_price=19.99, currency="EUR").finalize()]
    fresh = refresh.store_deals("steam", new, 390)
    alerts = asyncio.run(refresh.check_ai_watches(fresh, db.get_settings()))
    assert len(alerts) == 1 and alerts[0]["item"]["title"] == "Új Játék" and alerts[0]["reason"]
    # értelmezés + a frissítéskori döntés = 2 AI-hívás bela keretéből
    assert client.get("/api/meta").json()["ai_today"] == 2
    # elfogyott keret: az AI figyelő kimarad, nem hibázik
    with db.get_conn() as conn:
        conn.execute("UPDATE users SET ai_limit=2 WHERE id=?", (bela["id"],))
    more = [Deal(id="steam:Steam:1000", source="steam", store="Steam", title="Másik Játék", category="jatek",
                 price=0.99, old_price=9.99, currency="EUR").finalize()]
    fresh = refresh.store_deals("steam", new + more, 390)
    assert asyncio.run(refresh.check_ai_watches(fresh, db.get_settings())) == []


def test_ai_watch_requires_key_and_quota(client):
    register(client, "admin")
    r = client.post("/api/watches", json={"query": "olcsó jó játék", "use_ai": True})
    assert r.status_code == 400 and "Gemini" in r.json()["detail"]


def test_keyword_watch_does_not_touch_other_users_watches(client):
    seed()
    register(client, "admin")
    client.post("/api/watches", json={"query": "kivi"})
    client.post("/api/auth/logout")
    register(client, "bela")
    client.post("/api/watches", json={"query": "kivi"})
    client.post("/api/watches", json={"query": "sargarepa"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "admin", "password": "titok123"})
    assert len(client.get("/api/watches").json()["alerts"]) == 1


def test_ai_prefilter():
    items = [
        {"id": "a", "store": "Steam", "category": "jatek", "title": "Game", "price_huf": 800, "discount_pct": 80},
        {"id": "b", "store": "Lidl", "category": "elelmiszer", "title": "Kivi", "price_huf": 99, "discount_pct": 66},
        {"id": "c", "store": "Steam", "category": "jatek", "title": "Drága", "price_huf": 20000, "discount_pct": 10},
    ]
    got = refresh.ai_prefilter({"stores": ["Steam"], "category": "jatek", "max_price": 3000}, items)
    assert [i["id"] for i in got] == ["a"]
    assert refresh.ai_prefilter({}, items) == []  # túl általános: nem hívjuk az AI-t
    assert [i["id"] for i in refresh.ai_prefilter({"keywords": ["kivi"]}, items)] == ["b"]


def test_old_coupons_get_app_link_without_rescrape(client):
    """A régebbi verzióval eltárolt (app-link nélküli) kuponok is kapnak app-linket."""
    from app import db
    from app.scrapers.base import Deal

    refresh.store_deals("kfc", [Deal(id="kfc:KFC:x", source="kfc", store="KFC", title="Régi kupon",
                                     category="gyorsetterem", kind="coupon", price=990)], 390)
    with db.get_conn() as conn:
        assert conn.execute("SELECT extra FROM items WHERE id='kfc:KFC:x'").fetchone()[0] is None
    register(client)
    item = client.get("/api/coupons").json()["stores"]["KFC"][0]
    assert item["extra"]["app"]["link"] == "https://kfc.hu/kuponok"


def test_surprise_returns_good_random_offer_and_respects_exclude(client):
    seed()
    register(client)
    seen = set()
    for _ in range(15):
        item = client.get("/api/surprise").json()["item"]
        assert item["kind"] in ("deal", "coupon", "free_game")
        if item["kind"] == "deal" and item["category"] != "jatek":
            assert item["discount_pct"] >= 25
        seen.add(item["id"])
    # kizárás: ha mindent kizárunk, akkor is ad valamit (elölről kezdi)
    r = client.get("/api/surprise", params={"exclude": ",".join(seen)})
    assert r.status_code == 200 and r.json()["item"]


def test_surprise_empty_db(client):
    register(client)
    assert client.get("/api/surprise").status_code == 404
