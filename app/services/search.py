"""Lekérdezések: akciófolyam, kulcsszavas keresés, termék részletek, bevásárlólista."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from .. import db
from ..categories import normalize

SORTS = {
    "discount": "discount_pct DESC, (old_price_huf - price_huf) DESC",
    "savings": "(COALESCE(old_price_huf, price_huf) - price_huf) DESC, discount_pct DESC",
    "price": "price_huf IS NULL, price_huf ASC",
    "price_desc": "price_huf DESC",
    "unit_price": "unit_price IS NULL, unit_price ASC",
    "newest": "first_seen DESC, discount_pct DESC",
    "ending": "valid_to IS NULL, valid_to ASC, discount_pct DESC",
}

# Az Árfigyelőben ritkán előfordulnak hibás (pl. 95%+ "kedvezményes") adatok – ezeket kiszűrjük
MAX_SANE_DISCOUNT = 92


def _active_clause() -> tuple[str, list[Any]]:
    return "active=1 AND (valid_to IS NULL OR valid_to >= ?)", [db.now_iso()]


def _token_clause(tokens: list[str], mode: str = "AND") -> tuple[str, list[Any]]:
    """Szókezdet-illesztés a normalizált címen (" " + title_norm LIKE "% token%")."""
    if not tokens:
        return "", []
    parts = ["(' ' || title_norm) LIKE ?" for _ in tokens]
    return "(" + f" {mode} ".join(parts) + ")", [f"% {t}%" for t in tokens]


def list_deals(
    *,
    q: str = "",
    category: str = "",
    exclude_categories: list[str] | None = None,
    stores: list[str] | None = None,
    kinds: list[str] | None = None,
    min_discount: float | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    sort: str = "discount",
    favorites_only: bool = False,
    user_id: int | None = None,
    limit: int = 60,
    offset: int = 0,
) -> dict[str, Any]:
    kinds = kinds or ["deal"]
    where, params = _active_clause()
    clauses = [where, f"kind IN ({','.join('?' * len(kinds))})"]
    params += kinds
    if "deal" in kinds:
        clauses.append("(kind != 'deal' OR discount_pct <= ?)")
        params.append(MAX_SANE_DISCOUNT)
    tokens = normalize(q).split()
    if tokens:
        c, p = _token_clause(tokens)
        clauses.append(c)
        params += p
    if category:
        clauses.append("category = ?")
        params.append(category)
    elif exclude_categories:
        clauses.append(f"category NOT IN ({','.join('?' * len(exclude_categories))})")
        params += exclude_categories
    if stores:
        clauses.append(f"store IN ({','.join('?' * len(stores))})")
        params += stores
    if min_discount:
        clauses.append("discount_pct >= ?")
        params.append(min_discount)
    if min_price is not None:
        clauses.append("price_huf >= ?")
        params.append(min_price)
    if max_price is not None:
        clauses.append("price_huf <= ?")
        params.append(max_price)
    if favorites_only:
        clauses.append("id IN (SELECT item_id FROM favorites WHERE user_id=?)")
        params.append(user_id or 0)
    sql_where = " AND ".join(clauses)
    if sort == "mix":
        # "Legdurvább (vegyes)": körönként boltonként max. 3 tétel, a körön belül kedvezmény szerint,
        # így nem egyetlen bolt uralja a lista elejét
        query = (
            "SELECT * FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY store ORDER BY discount_pct DESC) rn "
            f"FROM items WHERE {sql_where}) ORDER BY (rn - 1) / 3, discount_pct DESC LIMIT ? OFFSET ?"
        )
    else:
        order = SORTS.get(sort, SORTS["discount"])
        query = f"SELECT * FROM items WHERE {sql_where} ORDER BY {order} LIMIT ? OFFSET ?"
    with db.get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM items WHERE {sql_where}", params).fetchone()[0]
        rows = conn.execute(query, params + [limit, offset]).fetchall()
        favs = {r[0] for r in conn.execute("SELECT item_id FROM favorites WHERE user_id=?", (user_id or 0,))}
    items = [db.row_to_dict(r) for r in rows]
    for it in items:
        it["favorite"] = it["id"] in favs
    return {"total": total, "items": items}


def keyword_candidates(
    keywords: list[str],
    *,
    category: str = "",
    min_price: float | None = None,
    max_price: float | None = None,
    stores: list[str] | None = None,
    min_discount: float | None = None,
    include_normal: bool = True,
    limit: int = 120,
) -> list[dict[str, Any]]:
    """Bármely kulcsszóra illeszkedő tételek, találatszám + kedvezmény szerint rangsorolva."""
    tokens: list[str] = []
    for kw in keywords:
        n = normalize(kw)
        if n and n not in tokens:
            tokens.append(n)
    if not tokens:
        return []
    where, params = _active_clause()
    kinds = ["deal", "coupon", "free_game"] + (["normal"] if include_normal else [])
    clauses = [
        where,
        f"kind IN ({','.join('?' * len(kinds))})",
        "(discount_pct IS NULL OR discount_pct <= ?)",
    ]
    params += kinds + [MAX_SANE_DISCOUNT]
    # A többszavas kulcsszavak minden szavának szerepelnie kell; a kulcsszavak között VAGY
    kw_parts, kw_params = [], []
    for t in tokens:
        c, p = _token_clause(t.split())
        kw_parts.append(c)
        kw_params += p
    clauses.append("(" + " OR ".join(kw_parts) + ")")
    params += kw_params
    if category:
        clauses.append("category = ?")
        params.append(category)
    if stores:
        clauses.append(f"store IN ({','.join('?' * len(stores))})")
        params += stores
    if min_price is not None:
        clauses.append("price_huf >= ?")
        params.append(min_price)
    if max_price is not None:
        clauses.append("price_huf <= ?")
        params.append(max_price)
    if min_discount:
        clauses.append("discount_pct >= ?")
        params.append(min_discount)
    with db.get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM items WHERE {' AND '.join(clauses)} "
            "ORDER BY (kind='deal') DESC, discount_pct DESC LIMIT 2000",
            params,
        ).fetchall()
    scored = []
    for r in rows:
        title = " " + r["title_norm"] + " "
        hits = sum(1 for t in tokens if all((" " + w) in title for w in t.split()))
        exact = sum(1 for t in tokens if (" " + t + " ") in title)
        scored.append((hits + exact * 0.5, r["kind"] == "deal", r["discount_pct"] or 0, r))
    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    return [db.row_to_dict(s[3]) for s in scored[:limit]]


def get_item(item_id: str, user_id: int | None = None) -> dict[str, Any] | None:
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        if not row:
            return None
        item = db.row_to_dict(row)
        history = [dict(r) for r in conn.execute(
            "SELECT day, price, old_price FROM price_history WHERE item_id=? ORDER BY day", (item_id,)
        )]
        others = []
        if item.get("product_key"):
            others = [db.row_to_dict(r) for r in conn.execute(
                "SELECT * FROM items WHERE product_key=? AND id!=? AND active=1 ORDER BY price_huf",
                (item["product_key"], item_id),
            )]
        item["favorite"] = bool(conn.execute(
            "SELECT 1 FROM favorites WHERE item_id=? AND user_id=?", (item_id, user_id or 0)
        ).fetchone())
    item["history"] = history
    item["other_stores"] = others
    item["price_check"] = price_check(item, history)
    return item


def price_check(item: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    """"Valódi akció?" – összevetés az elmúlt 30 nap árelőzményével."""
    price = item.get("price")
    if price is None or item.get("kind") not in ("deal", "normal"):
        return {"verdict": "unknown", "text": "Ehhez a tételhez nincs ár-összehasonlítás."}
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    today = db.today()
    past = [h for h in history if cutoff <= h["day"] < today and h["price"] is not None]
    if not past:
        return {
            "verdict": "unknown",
            "text": "Még nincs elég árelőzmény (az app az első naptól kezdve gyűjti).",
        }
    min_past = min(h["price"] for h in past)
    regular = max((h["old_price"] or h["price"]) for h in past)
    if price < min_past:
        return {"verdict": "good", "text": f"Az elmúlt 30 nap legalacsonyabb ára (eddig min. {min_past:.0f})."}
    if price == min_past:
        return {"verdict": "ok", "text": f"Ugyanannyi, mint az elmúlt 30 nap legjobb ára ({min_past:.0f})."}
    if item.get("old_price") and item["old_price"] > regular * 1.05:
        return {
            "verdict": "bad",
            "text": f"Gyanús: az „eredeti” ár magasabb, mint amennyiért korábban árulták ({regular:.0f}).",
        }
    return {"verdict": "meh", "text": f"Volt már olcsóbb is az elmúlt 30 napban: {min_past:.0f}."}


# ------------------------------------------------------------------ bevásárlólista
def shopping_candidates(line: str, limit: int = 40) -> list[dict[str, Any]]:
    """Egy bevásárlólista-tétel legvalószínűbb termékei, egységár szerint.

    AI nélkül is használható heurisztika:
      1. egész szavas egyezés előnyben ("tej" ne találja meg a "tejföl"-t),
      2. alkategória-szavazás (pl. "Tej", "Gyümölcs"): a kakukktojásokat
         ("tej és méz szappan", "banános tejbegríz") ez kiszűri.
    """
    tokens = normalize(line).split()
    if not tokens:
        return []
    where, params = _active_clause()
    c, p = _token_clause(tokens)
    with db.get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM items WHERE {where} AND kind IN ('deal','normal') "
            f"AND category NOT IN ('jatek','gyorsetterem') AND {c} "
            "AND (discount_pct IS NULL OR discount_pct <= ?) LIMIT 3000",
            params + p + [MAX_SANE_DISCOUNT],
        ).fetchall()
    items = [db.row_to_dict(r) for r in rows]
    if not items:
        return []

    def words(it: dict[str, Any]) -> list[str]:
        return normalize(it["title"]).replace(",", " ").replace(".", " ").split()

    def exact(it: dict[str, Any]) -> bool:
        w = set(words(it))
        return all(t in w for t in tokens)

    def group(it: dict[str, Any]) -> str:
        return it.get("subcategory") or it["category"]

    pool = [it for it in items if exact(it)] or items
    groups = {group(it) for it in pool}
    # 1) ha egy alkategória neve maga a keresett szó ("Rizs", "Tej", "Tojás", "Kenyérfélék"), az nyer
    named = [g for g in groups if any(w.startswith(tokens[0]) for w in normalize(g).split())]
    if named:
        top_sub = max(named, key=lambda g: sum(1 for it in pool if group(it) == g))
    else:
        # 2) szavazás: hány különböző boltban áll a szó a név elején (1. szó: 3 pont, 2. szó: 1 pont).
        #    Így a "Banán lédig" / "Alma Golden" nyer a sok "alma-banán bébidesszert" ellen.
        first: dict[str, set[str]] = defaultdict(set)
        second: dict[str, set[str]] = defaultdict(set)
        for it in pool:
            w = words(it)
            if w[:1] == [tokens[0]]:
                first[group(it)].add(it["store"])
            elif tokens[0] in w[1:2]:
                second[group(it)].add(it["store"])
        votes = {g: 3 * len(first[g]) + len(second[g]) for g in groups}
        if any(votes.values()):
            top_sub = max(votes, key=lambda g: (votes[g], g))
        else:
            top_sub = max(groups, key=lambda g: sum(1 for it in pool if group(it) == g))
    pool = [it for it in pool if group(it) == top_sub] or pool

    # a leggyakoribb mértékegység szerint hasonlítunk egységárat, különben a darabárat
    unit_counts: dict[str, int] = defaultdict(int)
    for it in pool:
        if it.get("unit") and it.get("unit_price"):
            unit_counts[it["unit"]] += 1
    main_unit = max(unit_counts, key=unit_counts.get) if unit_counts else None

    def cost(it: dict[str, Any]) -> float:
        if main_unit and it.get("unit") == main_unit and it.get("unit_price"):
            return float(it["unit_price"])
        return float(it.get("price_huf") or 1e12) * (1.5 if main_unit else 1.0)

    pool.sort(key=cost)
    return pool[:limit]


def build_shopping_plan(lines: list[str], allowed: dict[int, set[str]] | None = None) -> dict[str, Any]:
    results = []
    store_totals: dict[str, dict[str, Any]] = defaultdict(lambda: {"total": 0.0, "found": 0, "items": []})
    mixed_total = 0.0
    for i, line in enumerate(lines):
        cands = shopping_candidates(line)
        if allowed is not None and i in allowed:
            filtered = [c for c in cands if c["id"] in allowed[i]]
            cands = filtered or cands
        per_store: dict[str, dict[str, Any]] = {}
        for c in cands:
            if c.get("price_huf") is None:
                continue
            cur = per_store.get(c["store"])
            if cur is None or c["price_huf"] < cur["price_huf"]:
                per_store[c["store"]] = c
        best = min(per_store.values(), key=lambda c: c["price_huf"], default=None)
        if best:
            mixed_total += best["price_huf"]
        for store, c in per_store.items():
            st = store_totals[store]
            st["total"] += c["price_huf"]
            st["found"] += 1
            st["items"].append({"line": line, "id": c["id"], "title": c["title"], "price": c["price_huf"]})
        results.append({
            "line": line,
            "best": best,
            "per_store": sorted(per_store.values(), key=lambda c: c["price_huf"]),
        })
    stores = [
        {"store": s, **v, "total": round(v["total"])} for s, v in store_totals.items()
    ]
    stores.sort(key=lambda s: (-s["found"], s["total"]))
    return {
        "lines": results,
        "stores": stores,
        "mixed_total": round(mixed_total),
        "found": sum(1 for r in results if r["best"]),
    }
