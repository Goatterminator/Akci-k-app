"""GVH Árfigyelő (arfigyelo.gvh.hu) – állami árösszehasonlító.

Lefedi: Spar, Aldi, Tesco, Penny, Auchan, Lidl, dm, Rossmann, Müller.
Minden termékhez boltonként normál, akciós (DISCOUNTED) és hűségkártyás
(LOYALTY) árat ad, így nemcsak akciókat, hanem a bevásárlólista-optimalizáláshoz
szükséges normál árakat is innen vesszük.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .base import Deal, ScrapeContext, Scraper, get_with_retry

BASE = "https://arfigyelo.gvh.hu"
API = BASE + "/api"
PAGE_SIZE = 48  # az API ennél többet nem ad vissza egy kérésre

# Árfigyelő főkategória -> egységes kategória
TOP_CATEGORY_MAP = {
    1001: "elelmiszer",
    1015: "elelmiszer",
    1028: "elelmiszer",
    1046: "elelmiszer",
    1050: "elelmiszer",
    1068: "elelmiszer",
    1123: "baba",
    1126: "haztartas",
    1138: "drogeria",
}
# Alkategória felülírások
SUB_CATEGORY_MAP = {
    2061: "ital",  # Víz, gyümölcslé
    2101: "ital",  # Tea és kávé
}


def parse_products(products: list[dict[str, Any]], category: str, subcategory: str | None) -> list[Deal]:
    deals: list[Deal] = []
    for p in products:
        pid = str(p.get("id") or "")
        name = (p.get("name") or "").strip()
        if not pid or not name:
            continue
        unit = p.get("unit")
        cat_path = p.get("categoryPath") or ""
        url = f"{BASE}/k/{cat_path}/t/{pid}" if cat_path else BASE
        for store in p.get("pricesOfChainStores") or []:
            store_name = store.get("name") or "?"
            prices = store.get("prices") or []
            normal = next((x for x in prices if x.get("type") == "NORMAL"), None)
            promos = [x for x in prices if x.get("type") in ("DISCOUNTED", "LOYALTY") and x.get("amount")]
            best = min(promos, key=lambda x: x["amount"]) if promos else None
            current = best or normal
            if not current or not current.get("amount"):
                continue
            price = float(current["amount"])
            old_price = float(normal["amount"]) if (best and normal and normal.get("amount")) else None
            badge = None
            if best and best.get("type") == "LOYALTY":
                badge = "Hűségkártyás ár"
            deal = Deal(
                id=f"arfigyelo:{store_name}:{pid}",
                source="arfigyelo",
                store=store_name,
                title=name,
                category=category,
                subcategory=subcategory,
                kind="deal" if (best and old_price and price < old_price) else "normal",
                price=price,
                old_price=old_price,
                unit_price=current.get("unitAmount"),
                unit=unit,
                image=p.get("imageUrl"),
                url=url,
                badge=badge,
                product_key=f"ean:{pid}",
                extra={
                    "same_everywhere": store.get("priceSameEverywhere"),
                    "packaging": p.get("packaging"),
                },
            ).finalize()
            deals.append(deal)
    return deals


class ArfigyeloScraper(Scraper):
    name = "arfigyelo"
    label = "GVH Árfigyelő"
    stores = ["Spar", "Aldi", "Tesco", "Penny", "Auchan", "Lidl", "dm", "Rossmann", "Müller"]
    description = "Az állami árfigyelő adatai: élelmiszer, drogéria, háztartás 9 láncnál."

    concurrency = 3
    delay_s = 0.4

    async def fetch(self, ctx: ScrapeContext) -> list[Deal]:
        resp = await get_with_retry(ctx.client, f"{API}/categories")
        tree = resp.json().get("categories", [])
        targets: list[tuple[int, str, str]] = []
        for top in tree:
            top_cat = TOP_CATEGORY_MAP.get(top.get("id"), "elelmiszer")
            for sub in top.get("categoryNodes") or []:
                cat = SUB_CATEGORY_MAP.get(sub.get("id"), top_cat)
                targets.append((sub["id"], cat, sub.get("name") or top.get("name") or ""))
            if not top.get("categoryNodes"):
                targets.append((top["id"], top_cat, top.get("name") or ""))

        sem = asyncio.Semaphore(self.concurrency)
        results: list[Deal] = []

        async def page(cat_id: int, offset: int) -> dict[str, Any]:
            async with sem:
                r = await get_with_retry(
                    ctx.client,
                    f"{API}/products-by-category/{cat_id}",
                    params={"limit": PAGE_SIZE, "offset": offset, "order": "unitAmount_asc"},
                )
                await asyncio.sleep(self.delay_s)
                return r.json()

        async def crawl(cat_id: int, cat: str, subname: str) -> None:
            first = await page(cat_id, 0)
            total = int(first.get("count") or 0)
            results.extend(parse_products(first.get("products") or [], cat, subname))
            offsets = range(PAGE_SIZE, min(total, 3000), PAGE_SIZE)
            pages = await asyncio.gather(*(page(cat_id, o) for o in offsets), return_exceptions=True)
            for pg in pages:
                if isinstance(pg, Exception):
                    ctx.log.append(f"Árfigyelő {subname}: {pg}")
                    continue
                results.extend(parse_products(pg.get("products") or [], cat, subname))

        outcomes = await asyncio.gather(*(crawl(*t) for t in targets), return_exceptions=True)
        errors = [o for o in outcomes if isinstance(o, Exception)]
        if errors and len(errors) == len(targets):
            raise errors[0]
        for e in errors:
            ctx.log.append(f"Árfigyelő kategória hiba: {e}")

        # ugyanaz a termék több kategóriában is megjelenhet
        uniq: dict[str, Deal] = {}
        for d in results:
            uniq[d.id] = d
        return list(uniq.values())
