"""Forrás-regiszter. Új forrás hozzáadása: írj egy Scraper alosztályt és vedd fel ide."""
from __future__ import annotations

from .arfigyelo import ArfigyeloScraper
from .base import Deal, ScrapeContext, Scraper, SourceBlocked, make_client
from .emag import EmagScraper
from .fastfood import BurgerKingScraper, KfcScraper
from .games import EpicScraper, SteamScraper
from .lidl import LidlScraper

SCRAPERS: list[Scraper] = [
    ArfigyeloScraper(),
    LidlScraper(),
    KfcScraper(),
    BurgerKingScraper(),
    EpicScraper(),
    SteamScraper(),
    EmagScraper(),
]
SCRAPERS_BY_NAME: dict[str, Scraper] = {s.name: s for s in SCRAPERS}

__all__ = [
    "Deal", "ScrapeContext", "Scraper", "SourceBlocked", "make_client",
    "SCRAPERS", "SCRAPERS_BY_NAME",
]
