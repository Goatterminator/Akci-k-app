"""Google Gemini (ingyenes API kulcs) – REST hívások SDK nélkül.

Funkciók:
  * AI kereső: a szabad szöveges kérést kulcsszavakra bontja, majd a
    jelöltek közül kiválasztja és megindokolja a legjobb ajánlatokat.
  * Bevásárlólista pontosítás: kiszűri a nem odaillő találatokat (pl. "tej" -> nem tejföl).
  * Burger King kuponképekről az ár kiolvasása.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
from typing import Any

import httpx

from .. import db
from ..categories import CATEGORIES, STORES

log = logging.getLogger("akciok.gemini")

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-flash-latest"
# Első körös tartalékok. Ha ezek sem léteznek (a Google időnként kivezet modelleket),
# lekérdezzük a kulccsal ténylegesen elérhető modelleket, és azokból választunk.
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest"]
RETRYABLE_ON_NEXT_MODEL = {404, 429, 500, 503}
RETRY_DELAY_S = 1.5
MAX_DISCOVERED_TRIES = 4

# Ezek nem szöveges csevegő modellek, nem használhatók a kereséshez
_EXCLUDE = ("embedding", "tts", "image", "audio", "live", "native", "aqa", "robotics",
            "computer-use", "learnlm", "veo", "imagen", "thinking-exp", "vision")


LAST_MODEL: str | None = None  # az utoljára sikeresen válaszoló modell (a teszt gombhoz)


class GeminiError(Exception):
    pass


def has_key(settings: dict[str, str]) -> bool:
    return bool((settings.get("gemini_api_key") or "").strip())


def _version(name: str) -> float:
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return float(m.group(1)) if m else 0.0


def rank_models(names: list[str]) -> list[str]:
    """Használható modellek, a legjobb választás elöl: Flash > Flash-Lite > egyéb,
    stabil > preview/exp, `-latest` alias és újabb verzió előnyben."""
    usable = [n for n in names if n.startswith("gemini") and not any(x in n for x in _EXCLUDE)]

    def key(n: str):
        family = 0 if ("flash" in n and "lite" not in n) else 1 if "flash" in n else 2
        unstable = 1 if any(x in n for x in ("preview", "exp")) else 0
        return (family, unstable, 0 if n.endswith("-latest") else 1, -_version(n), n)

    return sorted(dict.fromkeys(usable), key=key)


async def list_models(settings: dict[str, str], client: httpx.AsyncClient | None = None,
                      force: bool = False) -> list[str]:
    """A kulccsal elérhető, szöveggenerálásra képes modellek (12 órán át gyorsítótárazva)."""
    key = (settings.get("gemini_api_key") or "").strip()
    if not key:
        raise GeminiError("Nincs megadva Gemini API kulcs (Beállítások).")
    cache_key = "gemini_models:" + hashlib.sha1(key.encode()).hexdigest()[:12]
    if not force:
        cached = db.cache_get(cache_key, max_age_s=12 * 3600)
        if cached:
            return cached
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=30)
    names: list[str] = []
    try:
        token = None
        for _ in range(10):
            params = {"pageSize": 1000}
            if token:
                params["pageToken"] = token
            resp = await client.get(MODELS_URL, params=params, headers={"x-goog-api-key": key}, timeout=30)
            if resp.status_code in (400, 401, 403):
                raise GeminiError("A Gemini API kulcs érvénytelen vagy nincs engedélyezve.")
            if resp.status_code >= 300:
                raise GeminiError(f"Nem sikerült lekérni a modelleket (HTTP {resp.status_code}).")
            data = resp.json()
            for m in data.get("models") or []:
                if "generateContent" in (m.get("supportedGenerationMethods") or []):
                    names.append((m.get("name") or "").removeprefix("models/"))
            token = data.get("nextPageToken")
            if not token:
                break
    except httpx.HTTPError as exc:
        raise GeminiError(f"Nem sikerült elérni a Gemini szervert ({exc}).") from exc
    finally:
        if own_client:
            await client.aclose()
    ranked = rank_models([n for n in names if n])
    db.cache_set(cache_key, ranked)
    return ranked


async def _post(client: httpx.AsyncClient, key: str, model: str, body: dict[str, Any]) -> httpx.Response:
    resp = None
    for attempt in range(2):  # túlterhelésnél rövid várakozás után még egyszer
        resp = await client.post(
            API.format(model=model),
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        if resp.status_code in (500, 503) and attempt == 0:
            await asyncio.sleep(RETRY_DELAY_S)
            continue
        break
    return resp


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
    model = (settings.get("gemini_model") or DEFAULT_MODEL).strip()
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": temperature},
    }
    if schema:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = schema

    own_client = client is None
    client = client or httpx.AsyncClient(timeout=60)
    resp: httpx.Response | None = None
    transport_error: Exception | None = None
    statuses: dict[str, int] = {}
    used_model = model
    try:
        queue = list(dict.fromkeys([model, *FALLBACK_MODELS]))
        discovered = False
        while queue:
            attempt_model = queue.pop(0)
            if attempt_model in statuses:
                continue
            try:
                resp = await _post(client, key, attempt_model, body)
            except httpx.HTTPError as exc:
                transport_error, resp = exc, None
                break
            statuses[attempt_model] = resp.status_code
            if resp.status_code < 300:
                used_model = attempt_model
                break
            if resp.status_code not in RETRYABLE_ON_NEXT_MODEL:
                break  # pl. rossz kulcs: másik modell sem segítene
            log.warning("Gemini %s: HTTP %s, próbálom a következő modellt", attempt_model, resp.status_code)
            if not queue and not discovered:
                # A beégetett nevek elfogytak: kérdezzük meg a Google-t, mi érhető el ezzel a kulccsal
                discovered = True
                try:
                    available = await list_models(settings, client)
                except GeminiError as exc:
                    log.warning("Modellek lekérése sikertelen: %s", exc)
                    available = []
                queue = [m for m in available if m not in statuses][:MAX_DISCOVERED_TRIES]
    finally:
        if own_client:
            await client.aclose()

    if resp is None:
        raise GeminiError(f"Nem sikerült elérni a Gemini szervert ({transport_error}). "
                          "Ellenőrizd a Pi internetkapcsolatát.")
    global LAST_MODEL
    if resp.status_code < 300:
        LAST_MODEL = used_model
    if resp.status_code < 300 and used_model != model:
        log.info("Gemini: %s helyett %s válaszolt", model, used_model)
        if statuses.get(model) == 404:
            # a beállított modell már nem létezik: elmentjük a működőt, hogy legközelebb azzal induljon
            db.set_settings({"gemini_model": used_model})
    if resp.status_code >= 300:
        codes = set(statuses.values())
        if codes & {500, 503}:
            raise GeminiError("A Google Gemini szervere most túlterhelt (HTTP 503). Ez nem a kulcsod hibája, "
                              "próbáld újra pár perc múlva.")
        if 429 in codes:
            raise GeminiError("Elérted az ingyenes Gemini keret percenkénti/napi limitjét. "
                              "Próbáld újra kicsit később.")
        if codes == {404}:
            raise GeminiError("Egyik próbált modell sem érhető el ezzel a kulccsal. Kattints az "
                              "„Elérhető modellek” gombra, és válassz a listából.")
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
_STORE_NAMES = list(STORES)

INTERPRET_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "keywords": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Magyar keresőszavak, ahogy termékcímekben szerepelnek (szinonimák, márkák, ragozatlan alak).",
        },
        "category": {"type": "STRING", "enum": _CATEGORY_KEYS + ["any"]},
        "stores": {
            "type": "ARRAY",
            "items": {"type": "STRING", "enum": _STORE_NAMES},
            "description": "Csak ha a kérés konkrét boltot/láncot említ (pl. 'steames' -> Steam).",
        },
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
    cache_key = "interpret2:" + hashlib.sha1(query.lower().encode()).hexdigest()
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
        "Ha a kérés konkrét boltot vagy platformot említ (pl. 'steames' -> Steam, 'lidlis' -> Lidl, "
        "'epices' -> Epic Games), add meg a stores listában; különben hagyd üresen. Boltok: "
        + ", ".join(_STORE_NAMES) + ". "
        "A sort mező: 'unit_price' ha a legolcsóbb egységár érdekli, 'price' ha a legolcsóbb, "
        "különben 'discount'."
    )
    result = await generate(settings, [{"text": prompt}], INTERPRET_SCHEMA)
    result["keywords"] = [k for k in (result.get("keywords") or []) if isinstance(k, str) and k.strip()][:15]
    if result.get("category") not in _CATEGORY_KEYS:
        result["category"] = ""
    result["stores"] = [s for s in (result.get("stores") or []) if s in STORES]
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
    if it.get("description"):  # pl. Steam értékelés: "Rendkívül pozitív – 95%..."
        parts.append(str(it["description"])[:90])
    return " | ".join(parts)


MATCH_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "matches": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"id": {"type": "STRING"}, "reason": {"type": "STRING"}},
                "required": ["id", "reason"],
            },
        }
    },
    "required": ["matches"],
}


async def match_watch(
    settings: dict[str, str], description: str, candidates: list[dict[str, Any]], limit: int = 10
) -> list[dict[str, str]]:
    """AI figyelő: a jelöltek közül azok, amelyek TÉNYLEG megfelelnek a leírásnak (indoklással)."""
    listing = "\n".join(_fmt_item(c) for c in candidates)
    prompt = (
        "Egy akciófigyelő app értesítést küld a felhasználónak, ha új ajánlat felel meg a figyelőjének.\n"
        f"A figyelő leírása: \"{description}\"\n\n"
        "Az alábbi ajánlatok közül válaszd ki azokat, amelyek TÉNYLEG megfelelnek a leírásnak. "
        "Légy szigorú, inkább kevesebbet válassz: csak olyanról szóljunk, aminek a felhasználó "
        "valószínűleg örülne. Értelmezés: 'olcsó' = alacsony ár vagy nagy kedvezmény; 'jó' = jó "
        "minőség, játéknál jó értékelés (pl. 'Nagyon pozitív', 80% felett). Legfeljebb "
        f"{limit} találat. Minden találathoz írj egy rövid magyar indoklást (max. 12 szó, pl. ár, "
        "kedvezmény, értékelés). Ha semmi sem illik, adj üres listát.\n"
        "Formátum soronként: id | bolt | név | ár | ...\n\n" + listing
    )
    result = await generate(settings, [{"text": prompt}], MATCH_SCHEMA, temperature=0.1)
    valid = {c["id"] for c in candidates}
    out, seen = [], set()
    for m in result.get("matches") or []:
        if m.get("id") in valid and m["id"] not in seen:
            seen.add(m["id"])
            out.append({"id": m["id"], "reason": str(m.get("reason") or "")[:160]})
    return out[:limit]


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
