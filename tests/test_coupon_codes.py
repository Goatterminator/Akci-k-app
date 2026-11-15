"""Online kuponkódok (Picodi): feldolgozás, boltkeresés, végpontok."""
import asyncio

from conftest import load

from app.services import coupon_codes as cc


def test_parse_slugs_from_sitemap():
    slugs = cc.parse_slugs(load("picodi_sitemap.xml"))
    assert "emag" in slugs and "mcdonalds" in slugs and "aboutyou-outlet" in slugs
    assert "" not in slugs  # a főoldal nem bolt


def test_parse_shop_page(monkeypatch):
    monkeypatch.setattr(cc, "datetime", _FixedDatetime)
    shop = cc.parse_shop(load("picodi_emag.html"), "emag")
    assert shop["name"] == "eMAG" and shop["logo"].startswith("https://cdn.picodi.com/")
    assert len(shop["offers"]) == 4
    first = shop["offers"][0]
    assert first["type"] == "code" and first["value"] == "20%"
    assert first["url"].startswith("https://www.picodi.com/hu/emag#cid=")
    assert first["expires"] == "2026-11-19"
    # kódok elöl, utána a sima akciók
    assert [o["type"] for o in shop["offers"]] == ["code", "code", "promo", "promo"]
    # a tiltott (robots.txt) útvonalakra nem linkelünk
    assert all("/coupon/" not in o["url"] and "/out" not in o["url"] for o in shop["offers"])


class _FixedDatetime(cc.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 15, 12, 0)


def test_expired_offers_are_hidden(monkeypatch):
    class Later(cc.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 12, 1)

    monkeypatch.setattr(cc, "datetime", Later)
    shop = cc.parse_shop(load("picodi_emag.html"), "emag")
    assert all(o["expires"] is None for o in shop["offers"])


def test_search_shops(fresh_db, monkeypatch):
    async def fake_slugs(client=None):
        return cc.parse_slugs(load("picodi_sitemap.xml"))

    monkeypatch.setattr(cc, "get_slugs", fake_slugs)
    got = asyncio.run(cc.search_shops("mcdon"))
    assert got[0] == {"slug": "mcdonalds", "name": "McDonald's"}
    about = [m["slug"] for m in asyncio.run(cc.search_shops("about"))]
    assert about == ["aboutyou", "aboutyou-outlet"]
    assert asyncio.run(cc.search_shops("x")) == []


def test_endpoints_reject_unknown_shop(client, monkeypatch):
    async def fake_slugs(client=None):
        return cc.parse_slugs(load("picodi_sitemap.xml"))

    monkeypatch.setattr(cc, "get_slugs", fake_slugs)
    client.post("/api/auth/register", json={"username": "admin", "password": "titok123"})
    assert client.get("/api/coupon-codes/shop/nincsilyen").status_code == 404
    assert client.get("/api/coupon-codes/shop/..%2Fetc").status_code in (400, 404)
    assert client.get("/api/coupon-codes/search?q=wol").json()["matches"][0]["slug"] == "wolt"


def test_shop_is_cached(fresh_db, monkeypatch):
    calls = []

    async def fake_slugs(client=None):
        return ["emag"]

    async def fake_get(client, url, **kw):
        calls.append(url)

        class R:
            text = load("picodi_emag.html")
        return R()

    monkeypatch.setattr(cc, "get_slugs", fake_slugs)
    monkeypatch.setattr(cc, "get_with_retry", fake_get)
    a = asyncio.run(cc.get_shop("emag"))
    b = asyncio.run(cc.get_shop("emag"))
    assert a == b and len(calls) == 1  # a második a gyorsítótárból jön
