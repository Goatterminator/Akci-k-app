"""eMAG.hu – KÍSÉRLETI.

Az eMAG AWS WAF captchával védekezik. A captchát szándékosan NEM kerüljük
meg: ha a kérést blokkolják, a forrás "blokkolva" állapotot jelez, és ennyi.
Otthoni (nem adatközponti) IP-ről, ritka lekéréssel gyakran átengedi.

A figyelt listaoldalak a Beállításokban módosíthatók (soronként egy URL).
"""
from __future__ import annotations

import asyncio
import re

from bs4 import BeautifulSoup

from ..categories import guess_category
from .base import Deal, ScrapeContext, Scraper, SourceBlocked, get_with_retry, parse_price

BASE = "https://www.emag.hu"
DEFAULT_URLS = [
    BASE + "/mobiltelefonok/sort-discountdesc/c",
    BASE + "/laptopok/sort-discountdesc/c",
    BASE + "/televiziok/sort-discountdesc/c",
    BASE + "/fulhallgatok/sort-discountdesc/c",
    BASE + "/okosorak/sort-discountdesc/c",
]


def _looks_blocked(text: str) -> bool:
    head = text[:5000].lower()
    return "captcha" in head and ("awswaf" in head or "szokatlanul nagy forgalmat" in head)


def parse_emag(page_html: str, listing_url: str = "") -> list[Deal]:
    soup = BeautifulSoup(page_html, "html.parser")
    deals: list[Deal] = []
    for card in soup.select("div.card-item"):
        title_el = card.select_one("a.card-v2-title") or card.select_one(".card-v2-title")
        title = (card.get("data-name") or (title_el.get_text(" ", strip=True) if title_el else "")).strip()
        if not title:
            continue
        link = title_el.get("href") if title_el and title_el.has_attr("href") else None
        new_el = card.select_one(".product-new-price")
        price = parse_price(new_el.get_text(" ")) if new_el else None
        if price is None:
            continue
        old_price = None
        for sel in (".product-old-price s", ".rrp-lp30d-content s", ".pricing.old s", "s"):
            el = card.select_one(sel)
            if el:
                old_price = parse_price(el.get_text(" "))
                if old_price:
                    break
        pct = None
        m = re.search(r"-\s?(\d{1,2})\s?%", card.get_text(" "))
        if m:
            pct = float(m.group(1))
        img_el = card.select_one("img")
        img = (img_el.get("src") or img_el.get("data-src")) if img_el else None
        pid = card.get("data-product-id") or card.get("data-offer-id") or (link or title)
        deals.append(
            Deal(
                id=f"emag:eMAG:{pid}",
                source="emag",
                store="eMAG",
                title=title,
                category=guess_category(title, listing_url, default="elektronika"),
                kind="deal",
                price=price,
                old_price=old_price,
                discount_pct=pct,
                image=img,
                url=link if link and link.startswith("http") else (BASE + link if link else listing_url),
            ).finalize()
        )
    return deals


class EmagScraper(Scraper):
    name = "emag"
    label = "eMAG (kísérleti)"
    stores = ["eMAG"]
    description = "Kedvezmény szerint rendezett eMAG listaoldalak. Captcha esetén kimarad."
    experimental = True

    async def fetch(self, ctx: ScrapeContext) -> list[Deal]:
        urls = [u.strip() for u in (ctx.settings.get("emag_urls") or "").splitlines() if u.strip()]
        urls = urls or DEFAULT_URLS
        deals: dict[str, Deal] = {}
        blocked = 0
        for url in urls:
            try:
                resp = await get_with_retry(ctx.client, url, retries=0)
            except SourceBlocked:
                blocked += 1
                break  # ha egyszer blokkolt, nem erőltetjük tovább
            if _looks_blocked(resp.text):
                blocked += 1
                break
            for d in parse_emag(resp.text, url):
                if d.kind == "deal":
                    deals[d.id] = d
            await asyncio.sleep(2.0)
        if blocked and not deals:
            raise SourceBlocked("Az eMAG captchával blokkolta a lekérést (ezt nem kerüljük meg).")
        return list(deals.values())
