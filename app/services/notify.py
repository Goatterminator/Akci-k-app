"""Push értesítés telefonra az ingyenes ntfy szolgáltatással (https://ntfy.sh).

A telefonra telepítsd az ntfy appot, iratkozz fel egy egyedi, nehezen kitalálható
topicra (pl. akciok-x7k2p9), és ugyanezt add meg a Beállításokban.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("akciok.notify")


async def send(settings: dict[str, str], title: str, message: str, click: str | None = None,
               tags: list[str] | None = None) -> bool:
    topic = (settings.get("ntfy_topic") or "").strip()
    if not topic:
        return False
    server = (settings.get("ntfy_server") or "https://ntfy.sh").rstrip("/")
    payload: dict[str, Any] = {"topic": topic, "title": title, "message": message, "tags": tags or ["shopping_cart"]}
    if click:
        payload["click"] = click
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(server, json=payload)
            resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        log.warning("ntfy küldés sikertelen: %s", exc)
        return False


def _price(item: dict[str, Any]) -> str:
    p = item.get("price_huf")
    if p is None:
        return ""
    s = f"{p:,.0f} Ft".replace(",", " ")
    if item.get("discount_pct"):
        s += f" (-{item['discount_pct']:.0f}%)"
    return s


async def send_alerts(alerts: list[dict[str, Any]], settings: dict[str, str]) -> None:
    """Riasztások küldése felhasználónként, mindenki a saját ntfy témájára."""
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for a in alerts:
        topic = (a["watch"].get("ntfy_topic") or "").strip()
        if topic:
            by_topic.setdefault(topic, []).append(a)
    for topic, items in by_topic.items():
        user_settings = {**settings, "ntfy_topic": topic}
        if len(items) <= 3:
            for a in items:
                it = a["item"]
                await send(
                    user_settings,
                    f"🔔 {a['watch']['query']}: {it['store']}",
                    f"{it['title']} – {_price(it)}" + (f"\n✨ {a['reason']}" if a.get("reason") else ""),
                    click=it.get("url"),
                )
        else:
            lines = [f"• {a['item']['store']}: {a['item']['title'][:60]} – {_price(a['item'])}" for a in items[:8]]
            if len(items) > 8:
                lines.append(f"…és még {len(items) - 8}")
            await send(user_settings, f"🔔 {len(items)} új találat a figyelőidre", "\n".join(lines))
