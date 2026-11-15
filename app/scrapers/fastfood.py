"""Gyorséttermi kuponok: KFC és Burger King.

A McDonald's ajánlatai csak a MyMcDonald's appban érhetők el, ezért azokat
a felületen kézzel lehet felvenni ("Saját akció hozzáadása").
"""
from __future__ import annotations

import html
import re
from typing import Any

from bs4 import BeautifulSoup

from .base import Deal, ScrapeContext, Scraper, get_with_retry, parse_price

KFC_URL = "https://kfc.hu/kuponok"
BK_API = "https://burgerking.hu/wp-json/wp/v2/coupons"
BK_PAGE = "https://burgerking.hu/kuponjaink/"


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


# ------------------------------------------------------------------ KFC
def parse_kfc(page_html: str) -> list[Deal]:
    soup = BeautifulSoup(page_html, "html.parser")
    deals: list[Deal] = []
    seen: set[str] = set()
    for idx, card in enumerate(soup.select("div.coupon")):
        name_el = card.select_one(".coupon-name")
        if not name_el:
            continue
        raw_name = _clean(name_el.get_text(" "))
        number = re.match(r"#\s*(\d+)\.?\s*", raw_name)
        name = raw_name[number.end():] if number else raw_name
        desc_el = card.select_one(".coupon-description")
        price_el = card.select_one(".coupon-price") or card.select_one(".kfc-price")
        img_el = card.select_one("img.product-img-desktop") or card.select_one(".product-img img")
        price = parse_price(price_el.get_text(" ")) if price_el else None
        key = f"{number.group(1) if number else idx}-{name}"
        if key in seen:
            continue
        seen.add(key)
        desc = _clean(desc_el.get_text(" ")) if desc_el else None
        deals.append(
            Deal(
                id=f"kfc:KFC:{re.sub(r'[^a-z0-9]+', '-', name.lower())[:60]}",
                source="kfc",
                store="KFC",
                title=name,
                category="gyorsetterem",
                kind="coupon",
                price=price,
                image=img_el.get("src") if img_el else None,
                url=KFC_URL,
                badge=f"Kupon #{number.group(1)}" if number else "Kupon",
                description=desc if desc and desc.lower() != name.lower() else None,
            )
        )
    return deals


class KfcScraper(Scraper):
    name = "kfc"
    label = "KFC"
    stores = ["KFC"]
    description = "A KFC app aktuális kuponjai árral."

    async def fetch(self, ctx: ScrapeContext) -> list[Deal]:
        resp = await get_with_retry(ctx.client, KFC_URL)
        return parse_kfc(resp.text)


# ------------------------------------------------------------------ Burger King
def _bk_image(item: dict[str, Any]) -> str | None:
    head_json = item.get("yoast_head_json") or {}
    for img in head_json.get("og_image") or []:
        if img.get("url"):
            return img["url"]
    m = re.search(r'property="og:image" content="([^"]+)"', item.get("yoast_head") or "")
    return m.group(1) if m else None


def parse_burgerking(items: list[dict[str, Any]]) -> list[Deal]:
    deals: list[Deal] = []
    for item in items:
        title = _clean((item.get("title") or {}).get("rendered"))
        # "K0442 Chicken fans" -> belső kód levágása
        code = re.match(r"(K\d{3,5})\s+", title)
        nice_title = title[code.end():] if code else title
        excerpt = _clean(re.sub(r"<[^>]+>", " ", (item.get("excerpt") or {}).get("rendered") or ""))
        deals.append(
            Deal(
                id=f"burgerking:Burger King:{item.get('id')}",
                source="burgerking",
                store="Burger King",
                title=excerpt or nice_title,
                category="gyorsetterem",
                kind="coupon",
                image=_bk_image(item),
                url=f"{BK_PAGE}?coupon={item.get('id')}",
                badge=f"Kupon {code.group(1)}" if code else "Kupon",
                description=nice_title if excerpt else None,
                extra={"needs_price_ocr": True},
            )
        )
    return deals


class BurgerKingScraper(Scraper):
    name = "burgerking"
    label = "Burger King"
    stores = ["Burger King"]
    description = "A BK app kuponjai. Az árat (ami csak a képen szerepel) a Gemini olvassa ki, ha van kulcs."

    async def fetch(self, ctx: ScrapeContext) -> list[Deal]:
        resp = await get_with_retry(ctx.client, BK_API, params={"per_page": 100})
        return parse_burgerking(resp.json())
