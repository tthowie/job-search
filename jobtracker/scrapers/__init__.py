"""Scraper registry.

Each scraper is a class with at least a ``fetch(site, settings)`` method that
yields ``Job`` objects. Look up by ``scraper`` name from ``config.json``.
"""

from __future__ import annotations

from .base import BaseScraper, JobStub
from .generic import GenericScraper
from .sanofi import SanofiScraper
from .msd import MSDScraper
from .gsk import GSKScraper


REGISTRY: dict[str, type[BaseScraper]] = {
    "generic": GenericScraper,
    "sanofi": SanofiScraper,
    "msd": MSDScraper,
    "gsk": GSKScraper,
}


def get_scraper(name: str) -> type[BaseScraper]:
    """Resolve a scraper name to its class. Falls back to GenericScraper."""
    return REGISTRY.get(name, GenericScraper)


__all__ = [
    "BaseScraper",
    "JobStub",
    "GenericScraper",
    "SanofiScraper",
    "MSDScraper",
    "GSKScraper",
    "REGISTRY",
    "get_scraper",
]
