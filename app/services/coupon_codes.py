"""Online kuponkódok a Picodi (picodi.com/hu) bolti oldalairól.

Szabálykövetés: a Picodi robots.txt szerint tiltott /hu/coupon/*, /hu/offer/*, /hu/search/
és /hu/out útvonalakat NEM használjuk. Csak a nyilvános oldaltérképet (sitemap) és a bolti
oldalakat olvassuk, ritkán és gyorsítótárazva. A kódot magát a Picodi oldalán lehet
felfedni (az app oda linkel), így a forrás látogatottságot is kap.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .. import db
from ..categories import normalize
from ..scrapers.base import get_with_retry, make_client

BASE = "https://www.picodi.com/hu/"
SITEMAP = BASE + "sitemap.xml"
SLUGS_TTL = 24 * 3600
SHOP_TTL = 6 * 3600

# Kiemelt boltok a felületen (a Picodi slugjai)
POPULAR = ["mcdonalds", "kfc", "burgerking", "wolt", "foodora", "bolt", "kifli", "emag", "allegro",
           "alza", "mediamarkt", "decathlon", "notino", "temu", "aliexpress", "booking"]
DEFAULT_SHOPS = ["mcdonalds", "wolt", "foodora"]  # a Kuponok oldal alján alapból ezek látszanak

_PRETTY = {"emag": "eMAG", "kfc": "KFC", "mcdonalds": "McDonald's", "burgerking": "Burger King",
           "aliexpress": "AliExpress", "mediamarkt": "MediaMarkt", "aboutyou": "About You",
           "ikea": "IKEA", "dm": "dm", "bolt": "Bolt", "temu": "Temu", "shein": "SHEIN"}

_EXPIRY_RE = re.compile(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.")


class CouponCodeError(Exception):
    pass


def pretty_name(slug: str) -> str:
    return _PRETTY.get(slug) or slug.replace("-", " ").title()


def parse_slugs(sitemap_xml: str) -> list[str]:
    slugs = re.findall(r"<loc>https://www\.picodi\.com/hu/([a-z0-9][a-z0-9-]*)</loc>", sitemap_xml)
    return sorted(set(slugs))


def parse_shop(page_html: str, slug: str) -> dict[str, Any]:
    soup = BeautifulSoup(page_html, "html.parser")
    name, logo = pretty_name(slug), None
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            import json

            data = json.loads(tag.string or "{}")
        except ValueError:
            continue
        ent = data.get("mainEntity") or {}
        if ent.get("@type") == "Store":
            name = ent.get("name") or name
            logo = ent.get("logo") or ent.get("image")
    if name and name.lower() == slug:
        name = pretty_name(slug)
    url = BASE + slug
    offers = []
    for el in soup.select("[data-offer-id]"):
        classes = el.get("class") or []
        title_el = el.select_one(".of__title")
        if not title_el:
            continue
        value_el = el.select_one(".discount__value")
        desc_el = el.select_one(".of__description")
        end_el = el.select_one(".of__offer-end-date")
        expires = None
        if end_el:
            m = _EXPIRY_RE.search(end_el.get_text(" "))
            if m:
                try:
                    expires = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
                except ValueError:
                    expires = None
        offer_id = el.get("data-offer-id")
        value = " ".join(value_el.get_text(" ").split()) if value_el else None
        huf = re.fullmatch(r"HUF\s?(\d+)", value or "")
        if huf:  # "HUF2000" -> "2 000 Ft"
            value = f"{int(huf.group(1)):,} Ft".replace(",", " ")
        offers.append({
            "id": offer_id,
            "type": "code" if "type-code" in classes else "promo",
            "value": value,
            "title": " ".join(title_el.get_text(" ").split()),
            "description": " ".join(desc_el.get_text(" ").split()) if desc_el else None,
            "expires": expires,
            # a Picodi saját oldalán, az adott ajánlatnál nyílik meg (ott fedhető fel a kód)
            "url": f"{url}#cid={offer_id}",
        })
    today = datetime.now().strftime("%Y-%m-%d")
    offers = [o for o in offers if not o["expires"] or o["expires"] >= today]
    offers.sort(key=lambda o: (o["type"] != "code", o["expires"] or "9999"))
    return {"slug": slug, "name": name, "logo": logo, "url": url, "offers": offers}


async def get_slugs(client: httpx.AsyncClient | None = None) -> list[str]:
    cached = db.cache_get("picodi_slugs", max_age_s=SLUGS_TTL)
    if cached:
        return cached
    own = client is None
    client = client or make_client()
    try:
        resp = await get_with_retry(client, SITEMAP, retries=1)
        slugs = parse_slugs(resp.text)
    except Exception as exc:  # noqa: BLE001
        stale = db.cache_get("picodi_slugs")
        if stale:
            return stale
        raise CouponCodeError(f"A kuponoldal most nem érhető el ({exc}).") from exc
    finally:
        if own:
            await client.aclose()
    if slugs:
        db.cache_set("picodi_slugs", slugs)
    return slugs


async def search_shops(query: str, limit: int = 8) -> list[dict[str, str]]:
    q = normalize(query).replace(" ", "")
    if len(q) < 2:
        return []
    slugs = await get_slugs()
    scored = []
    for s in slugs:
        flat = s.replace("-", "")
        name_flat = normalize(pretty_name(s)).replace(" ", "")
        if flat.startswith(q) or name_flat.startswith(q):
            scored.append((0, len(s), s))
        elif q in flat or q in name_flat:
            scored.append((1, len(s), s))
    scored.sort()
    return [{"slug": s, "name": pretty_name(s)} for _, _, s in scored[:limit]]


async def get_shop(slug: str, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    slugs = await get_slugs(client)
    if slug not in slugs:  # csak a sitemapben szereplő boltot kérjük le (nincs tetszőleges URL)
        raise CouponCodeError("Ilyen bolt nincs a kuponoldalon.")
    key = f"picodi_shop:{slug}"
    cached = db.cache_get(key, max_age_s=SHOP_TTL)
    if cached:
        return cached
    own = client is None
    client = client or make_client()
    try:
        resp = await get_with_retry(client, BASE + slug, retries=1)
        shop = parse_shop(resp.text, slug)
    except Exception as exc:  # noqa: BLE001
        stale = db.cache_get(key)
        if stale:
            return stale
        raise CouponCodeError(f"A(z) {pretty_name(slug)} kuponjai most nem érhetők el ({exc}).") from exc
    finally:
        if own:
            await client.aclose()
    db.cache_set(key, shop)
    return shop
