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
    # az admin létrehozása után a regisztráció alapból zárva van
    assert client.get("/api/settings").json()["allow_registration"] == "0"
    client.put("/api/settings", json={"allow_registration": "1"})

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


def test_registration_closed_after_admin_created(client):
    register(client)
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
