"""Játékok: Epic Games ingyenes játékai és Steam akciók."""
from __future__ import annotations

import asyncio
import html
import re
from datetime import datetime, timezone
from typing import Any

from .base import Deal, ScrapeContext, Scraper, get_with_retry, parse_price

EPIC_FREE = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
STEAM_SEARCH = "https://store.steampowered.com/search/results/"


# ------------------------------------------------------------------ Epic
def _epic_image(el: dict[str, Any]) -> str | None:
    images = {i.get("type"): i.get("url") for i in el.get("keyImages") or []}
    for t in ("OfferImageWide", "DieselStoreFrontWide", "Thumbnail", "OfferImageTall"):
        if images.get(t):
            return images[t]
    return next(iter(images.values()), None)


def _epic_slug(el: dict[str, Any]) -> str | None:
    for m in el.get("offerMappings") or []:
        if m.get("pageSlug"):
            return m["pageSlug"]
    for m in (el.get("catalogNs") or {}).get("mappings") or []:
        if m.get("pageSlug"):
            return m["pageSlug"]
    slug = el.get("productSlug") or el.get("urlSlug")
    return slug.split("/")[0] if slug else None


def parse_epic(payload: dict[str, Any], now: datetime | None = None) -> list[Deal]:
    now = now or datetime.now(timezone.utc)
    elements = (((payload.get("data") or {}).get("Catalog") or {}).get("searchStore") or {}).get(
        "elements"
    ) or []
    deals: list[Deal] = []
    for el in elements:
        promos = el.get("promotions") or {}
        total = (el.get("price") or {}).get("totalPrice") or {}
        decimals = ((total.get("currencyInfo") or {}).get("decimals")) or 2
        original = (total.get("originalPrice") or 0) / (10 ** decimals)
        currency = total.get("currencyCode") or "HUF"

        def offers(key: str) -> list[dict[str, Any]]:
            return [o for g in promos.get(key) or [] for o in g.get("promotionalOffers") or []]

        kind = None
        window: dict[str, Any] | None = None
        for o in offers("promotionalOffers"):
            if (o.get("discountSetting") or {}).get("discountPercentage") == 0:
                start = _iso(o.get("startDate"))
                end = _iso(o.get("endDate"))
                if (not start or start <= now) and (not end or end > now):
                    kind, window = "free_game", o
                    break
        if not kind:
            for o in offers("upcomingPromotionalOffers"):
                if (o.get("discountSetting") or {}).get("discountPercentage") == 0:
                    kind, window = "upcoming_free", o
                    break
        if not kind:
            continue
        slug = _epic_slug(el)
        deals.append(
            Deal(
                id=f"epic:Epic Games:{el.get('id')}",
                source="epic",
                store="Epic Games",
                title=el.get("title") or "?",
                category="jatek",
                kind=kind,
                price=0.0,
                old_price=original or None,
                discount_pct=100.0,
                currency=currency,
                image=_epic_image(el),
                url=f"https://store.epicgames.com/hu/p/{slug}" if slug else "https://store.epicgames.com/hu/free-games",
                valid_from=window.get("startDate") if window else None,
                valid_to=window.get("endDate") if window else None,
                badge="Ingyenes most" if kind == "free_game" else "Hamarosan ingyenes",
                description=(el.get("description") or "")[:400] or None,
                extra={"seller": (el.get("seller") or {}).get("name")},
            )
        )
    return deals


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class EpicScraper(Scraper):
    name = "epic"
    label = "Epic Games"
    stores = ["Epic Games"]
    description = "Az Epic Games Store heti ingyenes játékai (most és hamarosan)."

    async def fetch(self, ctx: ScrapeContext) -> list[Deal]:
        resp = await get_with_retry(
            ctx.client, EPIC_FREE, params={"locale": "hu", "country": "HU", "allowCountries": "HU"}
        )
        return parse_epic(resp.json())


# ------------------------------------------------------------------ Steam
_ROW_RE = re.compile(r'<a href="(https://store\.steampowered\.com/(?:app|sub|bundle)/[^"]+)"(.*?)</a>', re.S)


def parse_steam(results_html: str, eur_huf: float) -> list[Deal]:
    deals: list[Deal] = []
    for m in _ROW_RE.finditer(results_html):
        url, body = m.group(1), m.group(2)
        appid = re.search(r'data-ds-(?:appid|packageid|bundleid)="([\d,]+)"', body)
        title = re.search(r'<span class="title">(.*?)</span>', body, re.S)
        disc = re.search(r'data-discount="(\d+)"', body)
        orig = re.search(r'class="discount_original_price">([^<]+)<', body)
        final = re.search(r'class="discount_final_price[^"]*">([^<]+)<', body)
        img = re.search(r'<img src="([^"]+)"', body)
        review = re.search(r'search_review_summary (\w+)"[^>]*data-tooltip-html="([^"]+)"', body)
        if not (appid and title and final):
            continue
        final_txt = html.unescape(final.group(1)).strip()
        price = 0.0 if "ingyen" in final_txt.lower() or "free" in final_txt.lower() else parse_price(final_txt)
        old = parse_price(html.unescape(orig.group(1))) if orig else None
        if price is None:
            continue
        currency = "EUR" if "€" in final_txt or (orig and "€" in orig.group(1)) else "HUF"
        pct = float(disc.group(1)) if disc else None
        review_text = html.unescape(review.group(2)).replace("<br>", " – ") if review else None
        clean_url = url.split("?")[0]
        image = img.group(1) if img else None
        if image and "capsule_231x87" in image:
            image = image.replace("capsule_231x87", "header")
        deals.append(
            Deal(
                id=f"steam:Steam:{appid.group(1)}",
                source="steam",
                store="Steam",
                title=html.unescape(title.group(1)).strip(),
                category="jatek",
                kind="free_game" if price == 0 and pct == 100 else "deal",
                price=price,
                old_price=old,
                discount_pct=pct,
                currency=currency,
                image=image,
                url=clean_url,
                badge=("Ingyen megtartható" if price == 0 and pct == 100 else None),
                description=review_text,
                extra={
                    "review": review.group(1) if review else None,
                    "eur_huf": eur_huf if currency == "EUR" else None,
                },
            ).finalize()
        )
    return deals


class SteamScraper(Scraper):
    name = "steam"
    label = "Steam"
    stores = ["Steam"]
    description = "A legjobban értékelt akciós Steam játékok + ingyen megtartható játékok."
    pages = 4

    async def fetch(self, ctx: ScrapeContext) -> list[Deal]:
        deals: dict[str, Deal] = {}
        queries = [
            {"specials": 1, "sort_by": "Reviews_DESC"},  # legjobban értékelt akciós játékok
            {"specials": 1, "maxprice": "free"},          # 100%-os, ingyen megtartható
        ]
        for q_index, extra in enumerate(queries):
            pages = self.pages if q_index == 0 else 1
            for page in range(pages):
                params = {
                    "start": page * 50,
                    "count": 50,
                    "infinite": 1,
                    "cc": "hu",
                    "l": "hungarian",
                    "json": 1,
                    "category1": 998,  # csak játékok (nem DLC/soundtrack)
                    **extra,
                }
                resp = await get_with_retry(ctx.client, STEAM_SEARCH, params=params)
                payload = resp.json()
                for d in parse_steam(payload.get("results_html") or "", ctx.eur_huf):
                    deals[d.id] = d
                if (page + 1) * 50 >= int(payload.get("total_count") or 0):
                    break
                await asyncio.sleep(0.7)
        return [d for d in deals.values() if d.kind in ("deal", "free_game")]
