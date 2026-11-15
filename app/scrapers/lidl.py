"""Lidl Magyarország – a lidl.hu saját kereső API-ja.

Kedvezmény szerint csökkenő sorrendben lapozunk, amíg van kedvezményes termék.
Ez a nem-élelmiszer (Parkside, Silvercrest, ruha stb.) akciókat is lefedi.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from ..categories import guess_category, normalize
from .base import Deal, ScrapeContext, Scraper, get_with_retry

BASE = "https://www.lidl.hu"
SEARCH = BASE + "/q/api/search"
PAGE = 60


def _ts(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


_LEVEL2_MAP = [
    ("bor, sor", "ital"),
    ("baba", "baba"),
    ("barkacs", "barkacs"),
    ("lakas", "otthon"),
    ("konyha es haztartas", "otthon"),
    ("divat", "ruha"),
    ("sport", "sport"),
    ("allatellatas", "egyeb"),
]


def lidl_category(path: str, title: str, raw: str) -> str:
    """A Lidl kategóriaútvonal ("A szükség világai/<szint2>/<szint3>/...") -> egységes kategória."""
    parts = [normalize(p) for p in path.split("/")]
    level2 = parts[1] if len(parts) > 1 else ""
    level3 = parts[2] if len(parts) > 2 else ""
    if "elelmiszer" in level2:
        if level3.startswith(("italok", "kave")):
            return "ital"
        if level3.startswith(("kozmetikum", "drogeria")):
            return "drogeria"
        return "elelmiszer"
    for key, cat in _LEVEL2_MAP:
        if level2.startswith(key):
            return cat
    return guess_category(title, default="elelmiszer" if raw in ("Food", "F+V") else "egyeb")


def parse_items(items: list[dict[str, Any]]) -> list[Deal]:
    deals: list[Deal] = []
    for it in items:
        data = (it.get("gridbox") or {}).get("data")
        if not data:
            continue
        price_info = data.get("price") or {}
        price = price_info.get("price")
        if price is None:
            continue
        discount = price_info.get("discount") or {}
        old_price = price_info.get("oldPrice") or discount.get("deletedPrice")
        title = (data.get("fullTitle") or data.get("title") or "").strip()
        keyfacts = data.get("keyfacts") or {}
        cat_path = keyfacts.get("wonCategoryPrimary") or ""
        category = lidl_category(cat_path, title, data.get("category") or "")

        valid_from = valid_to = None
        badge_text = None
        stock = data.get("stockAvailability") or {}
        for info in stock.get("badgeInfoV2") or []:
            valid_from = _ts(info.get("validFrom")) or valid_from
            valid_to = _ts(info.get("validUntil")) or valid_to
            for b in info.get("badges") or []:
                badge_text = badge_text or b.get("text")

        badge = None
        if data.get("lidlPlus"):
            badge = "Lidl Plus ár"
        elif discount.get("bargainHintEnabled") and discount.get("bargainHintText"):
            badge = discount.get("bargainHintText")

        base_price = (price_info.get("basePrice") or {}).get("text")
        url_path = data.get("canonicalUrl") or data.get("canonicalPath") or ""
        deals.append(
            Deal(
                id=f"lidl:Lidl:{data.get('productId') or data.get('itemId') or it.get('code')}",
                source="lidl",
                store="Lidl",
                title=title,
                category=category,
                subcategory=cat_path.split("/")[-1] if cat_path else None,
                kind="deal",
                price=float(price),
                old_price=float(old_price) if old_price else None,
                discount_pct=discount.get("percentageDiscount"),
                unit=base_price,
                image=data.get("image"),
                url=BASE + url_path if url_path.startswith("/") else (url_path or BASE),
                valid_from=valid_from,
                valid_to=valid_to,
                badge=badge,
                description=badge_text,
                extra={"brand": (data.get("brand") or {}).get("name")},
            ).finalize()
        )
    return deals


class LidlScraper(Scraper):
    name = "lidl"
    label = "Lidl"
    stores = ["Lidl"]
    description = "A lidl.hu összes akciós terméke (élelmiszer és nem-élelmiszer)."
    max_pages = 15

    async def fetch(self, ctx: ScrapeContext) -> list[Deal]:
        deals: dict[str, Deal] = {}
        offset = 0
        for _ in range(self.max_pages):
            resp = await get_with_retry(
                ctx.client,
                SEARCH,
                params={
                    "assortment": "HU",
                    "locale": "hu_HU",
                    "version": "v2.0.0",
                    "q": "*",
                    "sort": "percentageDiscount-desc",
                    "fetchsize": PAGE,
                    "offset": offset,
                },
            )
            payload = resp.json()
            items = payload.get("items") or []
            page_deals = parse_items(items)
            discounted = [d for d in page_deals if d.kind == "deal"]
            for d in discounted:
                deals[d.id] = d
            offset += len(items)
            # rendezett lista: ha egy oldalon már nincs kedvezmény, végeztünk
            if not items or not discounted or offset >= int(payload.get("numFound") or 0):
                break
            await asyncio.sleep(0.5)
        return list(deals.values())
