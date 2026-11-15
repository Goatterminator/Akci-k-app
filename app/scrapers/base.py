"""Közös scraper infrastruktúra."""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from .. import config


@dataclass
class Deal:
    """Egy termék / ajánlat egy adott boltban."""

    id: str                      # globálisan egyedi: "<forrás>:<bolt>:<külső azonosító>"
    source: str
    store: str
    title: str
    category: str = "egyeb"
    kind: str = "deal"           # deal | normal | coupon | free_game | upcoming_free
    price: float | None = None
    old_price: float | None = None
    discount_pct: float | None = None
    currency: str = "HUF"
    unit_price: float | None = None
    unit: str | None = None
    image: str | None = None
    url: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    badge: str | None = None
    description: str | None = None
    subcategory: str | None = None
    product_key: str | None = None   # azonos termék különböző boltokban (pl. vonalkód)
    extra: dict[str, Any] = field(default_factory=dict)

    def finalize(self) -> "Deal":
        """Kedvezmény% kiszámítása, ha hiányzik, és értelmetlen adatok kiszűrése."""
        if self.old_price is not None and (
            self.old_price <= 0 or (self.price is not None and self.old_price <= self.price)
        ):
            self.old_price = None
        if self.discount_pct is None and self.price is not None and self.old_price:
            self.discount_pct = round((1 - self.price / self.old_price) * 100, 1)
        if self.discount_pct is not None:
            self.discount_pct = max(0.0, min(100.0, float(self.discount_pct)))
            if self.discount_pct == 0 and self.kind == "deal":
                self.discount_pct = None
        if self.kind == "deal" and not self.discount_pct:
            self.kind = "normal"
        return self


@dataclass
class ScrapeContext:
    settings: dict[str, str]
    client: httpx.AsyncClient
    log: list[str] = field(default_factory=list)

    @property
    def eur_huf(self) -> float:
        return eur_rate(self.settings)


def eur_rate(settings: dict[str, str]) -> float:
    try:
        return float(settings.get("eur_huf") or 390)
    except ValueError:
        return 390.0


class SourceBlocked(Exception):
    """A forrás blokkolta a kérést (captcha, 403...)."""


class Scraper:
    name: str = ""
    label: str = ""
    stores: list[str] = []
    description: str = ""
    experimental: bool = False

    async def fetch(self, ctx: ScrapeContext) -> list[Deal]:  # pragma: no cover - interfész
        raise NotImplementedError


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={
            "User-Agent": config.USER_AGENT,
            "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.6",
        },
        timeout=httpx.Timeout(30.0, connect=15.0),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
    )


async def get_with_retry(
    client: httpx.AsyncClient, url: str, *, retries: int = 2, **kwargs: Any
) -> httpx.Response:
    """GET, átmeneti hibáknál (5xx, timeout) néhány kíméletes újrapróbálással.

    403/429/511 esetén nem erőlködünk: ez blokkolást jelent.
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client.get(url, **kwargs)
            if resp.status_code in (403, 429, 511):
                raise SourceBlocked(f"A forrás blokkolta a kérést (HTTP {resp.status_code})")
            if resp.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
            resp.raise_for_status()
            return resp
        except SourceBlocked:
            raise
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                raise
            await asyncio.sleep(2 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


_PRICE_RE = re.compile(r"(\d[\d\s.  ]*)(?:[,](\d{1,2}))?")


def parse_price(text: str | None) -> float | None:
    """'1 299 Ft', '1.299,99 Ft', '20,49€' -> float."""
    if not text:
        return None
    text = text.replace(" ", " ").replace(" ", " ")
    m = _PRICE_RE.search(text)
    if not m:
        return None
    whole = re.sub(r"[\s.]", "", m.group(1))
    if not whole:
        return None
    value = float(whole)
    if m.group(2):
        value += float(m.group(2)) / (10 ** len(m.group(2)))
    return value
