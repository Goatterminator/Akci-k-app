"""Google Gemini (ingyenes API kulcs) – REST hívások SDK nélkül.

Funkciók:
  * AI kereső: a szabad szöveges kérést kulcsszavakra bontja, majd a
    jelöltek közül kiválasztja és megindokolja a legjobb ajánlatokat.
  * Bevásárlólista pontosítás: kiszűri a nem odaillő találatokat (pl. "tej" -> nem tejföl).
  * Burger King kuponképekről az ár kiolvasása.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any

import httpx

from .. import db
from ..categories import CATEGORIES

log = logging.getLogger("akciok.gemini")

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
FALLBACK_MODEL = "gemini-2.5-flash"


class GeminiError(Exception):
    pass


def has_key(settings: dict[str, str]) -> bool:
    return bool((settings.get("gemini_api_key") or "").strip())


async def generate(
    settings: dict[str, str],
    parts: list[dict[str, Any]],
    schema: dict[str, Any] | None = None,
    temperature: float = 0.2,
    client: httpx.AsyncClient | None = None,
) -> Any:
    key = (settings.get("gemini_api_key") or "").strip()
    if not key:
        raise GeminiError("Nincs megadva Gemini API kulcs (Beállítások).")
    model = (settings.get("gemini_model") or FALLBACK_MODEL).strip()
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": temperature},
    }
    if schema:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = schema

    own_client = client is None
    client = client or httpx.AsyncClient(timeout=60)
    try:
        for attempt_model in dict.fromkeys([model, FALLBACK_MODEL]):
            resp = await client.post(
                API.format(model=attempt_model),
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=body,
                timeout=60,
            )
            if resp.status_code == 404 and attempt_model != FALLBACK_MODEL:
                log.warning("Gemini modell nem található: %s, váltás: %s", attempt_model, FALLBACK_MODEL)
                continue
            break
    finally:
        if own_client:
            await client.aclose()

    if resp.status_code == 429:
        raise GeminiError("Elérted az ingyenes Gemini keret percenkénti/napi limitjét. Próbáld újra kicsit később.")
    if resp.status_code in (400, 401, 403):
        msg = ""
        try:
            msg = resp.json().get("error", {}).get("message", "")
        except ValueError:
            pass
        if "API key" in msg or resp.status_code in (401, 403):
            raise GeminiError("A Gemini API kulcs érvénytelen vagy nincs engedélyezve.")
        raise GeminiError(f"Gemini hiba: {msg or resp.status_code}")
    if resp.status_code >= 300:
        raise GeminiError(f"Gemini hiba (HTTP {resp.status_code})")

    data = resp.json()
    try:
        cand = data["candidates"][0]
        text = "".join(p.get("text", "") for p in cand["content"]["parts"] if not p.get("thought"))
    except (KeyError, IndexError):
        reason = (data.get("promptFeedback") or {}).get("blockReason") or "üres válasz"
        raise GeminiError(f"A Gemini nem adott választ ({reason}).")
    if schema:
        try:
            return json.loads(text)
        except ValueError as exc:
            raise GeminiError("A Gemini válasza nem értelmezhető.") from exc
    return text


# ------------------------------------------------------------------ AI kereső
_CATEGORY_KEYS = [c["key"] for c in CATEGORIES]

INTERPRET_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "keywords": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Magyar keresőszavak, ahogy termékcímekben szerepelnek (szinonimák, márkák, ragozatlan alak).",
        },
        "category": {"type": "STRING", "enum": _CATEGORY_KEYS + ["any"]},
        "max_price": {"type": "NUMBER", "nullable": True},
        "min_price": {"type": "NUMBER", "nullable": True},
        "sort": {"type": "STRING", "enum": ["discount", "price", "unit_price"]},
    },
    "required": ["keywords", "category", "sort"],
}

RANK_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "picks": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"id": {"type": "STRING"}, "reason": {"type": "STRING"}},
                "required": ["id", "reason"],
            },
        },
    },
    "required": ["summary", "picks"],
}


async def interpret_query(settings: dict[str, str], query: str) -> dict[str, Any]:
    cache_key = "interpret:" + hashlib.sha1(query.lower().encode()).hexdigest()
    cached = db.cache_get(cache_key, max_age_s=7 * 86400)
    if cached:
        return cached
    prompt = (
        "Egy budapesti akciófigyelő app keresőjét segíted. A felhasználó ezt keresi:\n"
        f"\"{query}\"\n\n"
        "Adj vissza 3-15 rövid magyar keresőszót (szótő, ékezettel), amelyekkel a boltok "
        "termékcímeiben megtalálható a keresett termék (pl. 'mosópor' -> mosópor, mosógél, "
        "mosókapszula, Ariel, Persil). Ha ár szerepel a kérésben, töltsd ki a max_price/min_price "
        "mezőt forintban (euró esetén váltsd át ~390 Ft/€ árfolyamon). Válassz kategóriát, ha "
        "egyértelmű, különben 'any'. Kategóriák: " + ", ".join(_CATEGORY_KEYS) + ". "
        "A sort mező: 'unit_price' ha a legolcsóbb egységár érdekli, 'price' ha a legolcsóbb, "
        "különben 'discount'."
    )
    result = await generate(settings, [{"text": prompt}], INTERPRET_SCHEMA)
    result["keywords"] = [k for k in (result.get("keywords") or []) if isinstance(k, str) and k.strip()][:15]
    if result.get("category") not in _CATEGORY_KEYS:
        result["category"] = ""
    db.cache_set(cache_key, result)
    return result


def _fmt_item(it: dict[str, Any]) -> str:
    parts = [it["id"], it["store"], it["title"]]
    price = it.get("price_huf")
    parts.append(f"{price:.0f} Ft" if price is not None else "ár ismeretlen")
    if it.get("old_price_huf"):
        parts.append(f"eredeti {it['old_price_huf']:.0f} Ft")
    if it.get("discount_pct"):
        parts.append(f"-{it['discount_pct']:.0f}%")
    if it.get("unit_price") and it.get("unit"):
        parts.append(f"egységár {it['unit_price']:.0f} Ft/{it['unit']}")
    if it.get("badge"):
        parts.append(it["badge"])
    return " | ".join(parts)


async def rank_candidates(
    settings: dict[str, str], query: str, candidates: list[dict[str, Any]], limit: int = 12
) -> dict[str, Any]:
    listing = "\n".join(_fmt_item(c) for c in candidates)
    prompt = (
        "Te egy segítőkész magyar vásárlási asszisztens vagy egy akciófigyelő appban.\n"
        f"A felhasználó kérése: \"{query}\"\n\n"
        "Az alábbi aktuális ajánlatok közül válaszd ki a kéréshez valóban illő, legjobb "
        f"legfeljebb {limit} terméket (ár/érték, kedvezmény, egységár alapján). Csak olyan "
        "terméket válassz, ami tényleg megfelel a kérésnek; ha semmi sem illik, adj üres listát. "
        "Minden választáshoz írj egy rövid (max 1 mondatos) magyar indoklást. "
        "A summary 1-3 mondatban foglalja össze a legjobb lehetőséget és adjon tippet. "
        "Formátum soronként: id | bolt | név | ár | ...\n\n" + listing
    )
    result = await generate(settings, [{"text": prompt}], RANK_SCHEMA, temperature=0.3)
    valid = {c["id"] for c in candidates}
    result["picks"] = [p for p in result.get("picks") or [] if p.get("id") in valid][:limit]
    return result


# ------------------------------------------------------------------ bevásárlólista
FILTER_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "lines": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "index": {"type": "INTEGER"},
                    "ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": ["index", "ids"],
            },
        }
    },
    "required": ["lines"],
}


async def filter_shopping_candidates(
    settings: dict[str, str], lines: list[str], candidates: list[list[dict[str, Any]]]
) -> dict[int, set[str]]:
    blocks = []
    for i, (line, cands) in enumerate(zip(lines, candidates)):
        if not cands:
            continue
        blocks.append(f"### {i}: {line}\n" + "\n".join(f"{c['id']} | {c['title']}" for c in cands))
    if not blocks:
        return {}
    prompt = (
        "Bevásárlólista tételeihez kerestünk termékeket. Minden tételnél add vissza azoknak a "
        "találatoknak az id-ját, amelyek TÉNYLEG a keresett termékek (pl. 'tej' -> tej igen, "
        "tejföl/tejcsoki nem; 'csirkemell' -> nyers csirkemell igen, csirkemell-sonka nem). "
        "Az index a tétel sorszáma.\n\n" + "\n\n".join(blocks)
    )
    result = await generate(settings, [{"text": prompt}], FILTER_SCHEMA, temperature=0.0)
    out: dict[int, set[str]] = {}
    for line in result.get("lines") or []:
        if isinstance(line.get("index"), int):
            out[line["index"]] = set(line.get("ids") or [])
    return out


# ------------------------------------------------------------------ kuponkép -> ár
PRICE_SCHEMA = {
    "type": "OBJECT",
    "properties": {"price": {"type": "NUMBER", "nullable": True}},
    "required": ["price"],
}


async def enrich_coupon_prices(deals: list[Any], settings: dict[str, str], client: httpx.AsyncClient) -> None:
    """Ha van kulcs, a kuponképről kiolvassa a forint árat (képenként egyszer, gyorsítótárazva)."""
    for deal in deals:
        if not deal.extra.get("needs_price_ocr") or deal.price is not None or not deal.image:
            continue
        cache_key = "couponprice:" + deal.image
        cached = db.cache_get(cache_key)
        if cached is not None:
            deal.price = cached.get("price")
            continue
        if not has_key(settings):
            continue
        try:
            img = await client.get(deal.image)
            img.raise_for_status()
            mime = img.headers.get("content-type", "image/jpeg").split(";")[0]
            result = await generate(
                settings,
                [
                    {"inline_data": {"mime_type": mime, "data": base64.b64encode(img.content).decode()}},
                    {"text": "Ez egy gyorséttermi kupon. Mi a kuponon feltüntetett fizetendő ár forintban? "
                             "Ha nincs ár a képen, price legyen null."},
                ],
                PRICE_SCHEMA,
                temperature=0.0,
                client=client,
            )
        except (GeminiError, httpx.HTTPError) as exc:
            log.info("Kuponár kiolvasás sikertelen (%s): %s", deal.title, exc)
            if isinstance(exc, GeminiError) and "limit" in str(exc):
                return
            continue
        price = result.get("price")
        if isinstance(price, (int, float)) and 50 <= price <= 50000:
            deal.price = float(price)
        db.cache_set(cache_key, {"price": deal.price})
