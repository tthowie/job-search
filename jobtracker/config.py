"""Configuration loading / saving.

The config lives in ``config.json`` next to ``jobs.py``. If it doesn't exist
yet, we copy ``config.default.json`` to it on first run.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
DEFAULT_CONFIG_PATH = ROOT / "config.default.json"
DATA_DIR = ROOT / "data"
FETCHED_CSV = DATA_DIR / "fetched.csv"
KEPT_CSV = DATA_DIR / "kept.csv"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class Site:
    id: str
    name: str
    scraper: str          # "sanofi" | "msd" | "gsk" | "generic" | ...
    url: str
    enabled: bool = True


@dataclass
class GlobalSettings:
    keywords: list[str] = field(default_factory=list)
    location: str = ""
    max_jobs_per_site: int = 60


@dataclass
class Config:
    global_settings: GlobalSettings
    sites: list[Site]

    # ---- IO ---------------------------------------------------------------

    @classmethod
    def load(cls) -> "Config":
        DATA_DIR.mkdir(exist_ok=True)
        if not CONFIG_PATH.exists():
            if DEFAULT_CONFIG_PATH.exists():
                shutil.copy(DEFAULT_CONFIG_PATH, CONFIG_PATH)
            else:  # ultimate fallback
                CONFIG_PATH.write_text(json.dumps({
                    "global": asdict(GlobalSettings()),
                    "sites": [],
                }, indent=2))
        raw = json.loads(CONFIG_PATH.read_text())
        gs = GlobalSettings(**raw.get("global", {}))
        sites = [Site(**s) for s in raw.get("sites", [])]
        return cls(global_settings=gs, sites=sites)

    def save(self) -> None:
        payload: dict[str, Any] = {
            "global": asdict(self.global_settings),
            "sites": [asdict(s) for s in self.sites],
        }
        CONFIG_PATH.write_text(json.dumps(payload, indent=2))

    # ---- Site management --------------------------------------------------

    def get_site(self, site_id: str) -> Site | None:
        for s in self.sites:
            if s.id == site_id:
                return s
        return None

    def add_site(self, site: Site) -> None:
        if self.get_site(site.id) is not None:
            raise ValueError(f"Site '{site.id}' already exists")
        self.sites.append(site)

    def remove_site(self, site_id: str) -> bool:
        before = len(self.sites)
        self.sites = [s for s in self.sites if s.id != site_id]
        return len(self.sites) != before
