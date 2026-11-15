"""Parser tesztek valódi (megvágott) forrásválaszokon."""
from datetime import datetime, timezone

from conftest import load

from app.categories import guess_category, normalize
from app.scrapers.arfigyelo import parse_products
from app.scrapers.base import Deal, parse_price
from app.scrapers.emag import _looks_blocked, parse_emag
from app.scrapers.fastfood import parse_burgerking, parse_kfc
from app.scrapers.games import parse_epic, parse_steam
from app.scrapers.lidl import lidl_category, parse_items


def test_parse_price_formats():
    assert parse_price("1 299 Ft") == 1299
    assert parse_price("1.299,99 Ft") == 1299.99
    assert parse_price("20,49€") == 20.49
    assert parse_price("1 750 Ft") == 1750
    assert parse_price("") is None


def test_deal_finalize_computes_discount_and_drops_bogus_old_price():
    d = Deal(id="x", source="t", store="s", title="t", price=75, old_price=100).finalize()
    assert d.discount_pct == 25 and d.kind == "deal"
    d = Deal(id="x", source="t", store="s", title="t", price=100, old_price=90).finalize()
    assert d.old_price is None and d.kind == "normal"


def test_normalize_and_category():
    assert normalize("Mosogatószer  ÚJ!") == "mosogatoszer uj"
    assert guess_category("PARKSIDE Akkus fúró") == "barkacs"
    assert guess_category("Sorozat DVD") != "ital"  # "sor " csak egész szóra illeszkedik


def test_arfigyelo_parse():
    deals = parse_products(load("arfigyelo_products.json")["products"], "elelmiszer", "Tészta")
    assert deals
    promo = [d for d in deals if d.kind == "deal"]
    assert promo, "a fixture-ben van akciós ár"
    for d in promo:
        assert d.old_price > d.price and 0 < d.discount_pct < 100
        assert d.url.startswith("https://arfigyelo.gvh.hu/k/")
        assert d.product_key.startswith("ean:")
    assert any(d.badge == "Hűségkártyás ár" for d in deals)


def test_lidl_parse_and_category():
    deals = parse_items(load("lidl_search.json")["items"])
    assert len(deals) == 6
    kivi = next(d for d in deals if d.title == "Arany kivi")
    assert kivi.price == 99 and kivi.old_price == 299 and kivi.discount_pct == 66
    assert kivi.category == "elelmiszer" and kivi.valid_to
    assert lidl_category("A szükség világai/Barkácsáruház és kert/Akkus", "x", "NonFood") == "barkacs"
    assert lidl_category("A szükség világai/Élelmiszer és élelmiszer-közeli élelmiszerek/Italok", "x", "") == "ital"


def test_epic_free_and_upcoming():
    now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    deals = {d.title: d for d in parse_epic(load("epic_free.json"), now=now)}
    assert deals["Knightica"].kind == "free_game"
    assert deals["Knightica"].old_price == 5350 and deals["Knightica"].price == 0
    assert deals["Alien: Isolation"].kind == "upcoming_free"
    assert "Them's Fightin' Herds" not in deals  # nincs ingyenes promóciója


def test_steam_parse():
    deals = parse_steam(load("steam_results.html"), eur_huf=390)
    assert len(deals) == 4
    for d in deals:
        assert d.currency == "EUR" and d.category == "jatek"
        assert d.old_price > d.price and d.discount_pct
        assert d.url.startswith("https://store.steampowered.com/app/")


def test_kfc_parse():
    deals = parse_kfc(load("kfc_coupons.html"))
    assert len(deals) == 3
    assert deals[0].title == "2xSajtburger + kis sült burgonya"
    assert deals[0].price == 1750 and deals[0].kind == "coupon"


def test_burgerking_parse():
    deals = parse_burgerking(load("burgerking_coupons.json"))
    assert len(deals) == 2
    assert all(d.image and d.extra.get("needs_price_ocr") for d in deals)
    assert all(not d.title.startswith("K0") for d in deals)


def test_emag_parse_and_block_detection():
    html = """
    <div class="card-item" data-product-id="123" data-name="Okostelefon X">
      <a class="card-v2-title" href="https://www.emag.hu/okostelefon-x/pd/1/">Okostelefon X</a>
      <img src="https://img/x.jpg">
      <p class="product-old-price"><s>100.000 Ft</s></p>
      <p class="product-new-price">74.990 Ft</p>
    </div>"""
    deals = parse_emag(html)
    assert len(deals) == 1 and deals[0].price == 74990 and deals[0].old_price == 100000
    assert deals[0].discount_pct == 25.0
    assert _looks_blocked("<title>eMAG Captcha</title> awswaf szokatlanul nagy forgalmat")
