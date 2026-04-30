"""Base scraper class with shared HTTP and HTML parsing helpers.

Each concrete scraper implements:

- ``list_jobs(self) -> Iterable[JobStub]``  — return at minimum URL+title
- ``fetch_details(self, stub) -> Job``      — visit URL, extract all fields

The base class provides ``fetch(...)`` which orchestrates: list, dedupe,
filter by keywords/location, fetch details, return Jobs.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from ..config import GlobalSettings, Site
from ..storage import Job

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Light job stub — the minimum we know after a search-page parse
# ---------------------------------------------------------------------------

@dataclass
class JobStub:
    url: str
    title: str = ""
    company: str = ""
    location: str = ""


# ---------------------------------------------------------------------------
# Common qualifications / deadline section header patterns
# ---------------------------------------------------------------------------

QUAL_HEADINGS = re.compile(
    r"(?:qualifications?|requirements?|required\s+skills?|"
    r"who\s+you\s+are|about\s+you|what\s+you'?ll\s+need|skills?\s*[:&]?\s*"
    r"experience)",
    re.IGNORECASE,
)

DESC_HEADINGS = re.compile(
    r"(?:about\s+the\s+(role|job|position)|job\s+description|"
    r"description|responsibilities|what\s+you'?ll\s+do|the\s+role|"
    r"role\s+(summary|overview)|purpose)",
    re.IGNORECASE,
)

DEADLINE_PAT = re.compile(
    r"(?:closing\s+date|deadline|applications?\s+close|apply\s+by|"
    r"close[sd]?\s+on|posted)\s*[:\-]?\s*"
    r"(\d{1,2}[\s\/\-\.](?:\d{1,2}|[A-Za-z]{3,9})[\s\/\-\.]\d{2,4}|"
    r"[A-Za-z]{3,9}\s+\d{1,2}(?:,\s*|\s+)\d{2,4})",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Base scraper
# ---------------------------------------------------------------------------

class BaseScraper:
    """Override ``list_jobs`` and (optionally) ``fetch_details``."""

    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Safari/605.1.15"
    )

    REQUEST_TIMEOUT = 20
    REQUEST_DELAY = 0.6  # seconds, polite throttle between detail fetches

    def __init__(self, site: Site, settings: GlobalSettings):
        self.site = site
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        })

    # ---------- HTTP helpers -------------------------------------------------

    def get(self, url: str, **kwargs) -> requests.Response | None:
        try:
            r = self.session.get(url, timeout=self.REQUEST_TIMEOUT, **kwargs)
            if r.status_code >= 400:
                log.warning("GET %s -> %s", url, r.status_code)
                return None
            return r
        except requests.RequestException as e:
            log.warning("GET %s failed: %s", url, e)
            return None

    def get_html(self, url: str) -> BeautifulSoup | None:
        r = self.get(url)
        if not r:
            return None
        return BeautifulSoup(r.text, "lxml")

    def get_json(self, url: str, **kwargs) -> dict | list | None:
        r = self.get(url, **kwargs)
        if not r:
            return None
        try:
            return r.json()
        except ValueError:
            return None

    # ---------- API to override ---------------------------------------------

    def list_jobs(self) -> Iterable[JobStub]:
        """Yield JobStub objects from the search page / API."""
        return []

    def fetch_details(self, stub: JobStub) -> Job:
        """Visit the job detail URL and parse description, qualifications, deadline."""
        soup = self.get_html(stub.url)
        title = stub.title
        description = ""
        qualifications = ""
        deadline = ""
        if soup is not None:
            title = title or self._extract_title(soup)
            description = self._extract_section(soup, DESC_HEADINGS)
            qualifications = self._extract_section(soup, QUAL_HEADINGS)
            if not description:
                # Fall back to first big <div> with substantial text
                description = self._extract_main_text(soup)[:3000]
            deadline = self._extract_deadline(soup)
        return Job(
            url=stub.url,
            title=title,
            company=stub.company or self.site.name,
            description=description,
            qualifications=qualifications,
            deadline=deadline,
            location=stub.location,
            site_id=self.site.id,
        )

    # ---------- Filters ------------------------------------------------------

    def keyword_match(self, text: str) -> bool:
        kws = [k.lower() for k in self.settings.keywords if k.strip()]
        if not kws:
            return True
        t = text.lower()
        return any(k in t for k in kws)

    def location_match(self, location: str) -> bool:
        loc_pref = self.settings.location.strip().lower()
        if not loc_pref:
            return True
        if not location:
            # If we don't know the location, don't filter it out — better to
            # err on the side of showing it than to drop it silently.
            return True
        return loc_pref in location.lower()

    # ---------- Top-level orchestrator --------------------------------------

    def fetch(self) -> list[Job]:
        out: list[Job] = []
        seen: set[str] = set()
        max_jobs = max(self.settings.max_jobs_per_site, 1)
        for stub in self.list_jobs():
            if not stub.url or stub.url in seen:
                continue
            seen.add(stub.url)

            # Cheap filtering on title before we hit the detail page
            if stub.title and not self.keyword_match(stub.title):
                # We'll still allow it through if no keywords are configured,
                # since keyword_match returns True in that case.
                # Keep going to detail page only if title matches.
                continue
            if not self.location_match(stub.location):
                continue

            try:
                job = self.fetch_details(stub)
            except Exception as e:  # noqa: BLE001
                log.warning("detail parse failed for %s: %s", stub.url, e)
                continue

            # Final keyword check using full text
            haystack = " ".join([
                job.title, job.description, job.qualifications,
            ])
            if not self.keyword_match(haystack):
                continue

            out.append(job)
            if len(out) >= max_jobs:
                break
            time.sleep(self.REQUEST_DELAY)
        return out

    # ---------- Soup helpers -------------------------------------------------

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        for sel in ["h1", 'meta[property="og:title"]', "title"]:
            el = soup.select_one(sel)
            if el:
                txt = el.get("content") if el.name == "meta" else el.get_text(" ", strip=True)
                if txt:
                    return txt.strip()
        return ""

    @staticmethod
    def _clean(text: str) -> str:
        # Collapse whitespace; drop boilerplate cookie/JS noise
        text = re.sub(r"\s+", " ", text or "").strip()
        return text

    def _extract_section(self, soup: BeautifulSoup, header_pat: "re.Pattern[str]") -> str:
        """Find a heading whose text matches ``header_pat`` and return the
        section's text (everything until the next heading of equal/higher level)."""
        for tag_name in ["h2", "h3", "h4", "strong", "b"]:
            for h in soup.find_all(tag_name):
                heading_txt = h.get_text(" ", strip=True)
                if not heading_txt or not header_pat.search(heading_txt):
                    continue
                # Walk siblings until next heading
                pieces: list[str] = []
                for sib in h.next_siblings:
                    if getattr(sib, "name", None) in {"h1", "h2", "h3", "h4"}:
                        break
                    if hasattr(sib, "get_text"):
                        pieces.append(sib.get_text(" ", strip=True))
                    else:
                        pieces.append(str(sib))
                blob = self._clean(" ".join(p for p in pieces if p))
                if len(blob) > 30:
                    return blob[:4000]
        # As a fallback for sites that put all content in one block,
        # search for inline phrases like "Qualifications:" or "Requirements:"
        body_text = soup.get_text(" ", strip=True)
        m = header_pat.search(body_text)
        if m:
            start = m.end()
            chunk = body_text[start : start + 2000]
            return self._clean(chunk)
        return ""

    def _extract_main_text(self, soup: BeautifulSoup) -> str:
        # Heuristic: pick the largest <main>/<article>/<section>/<div>
        candidates = soup.find_all(["main", "article", "section", "div"])
        best = ""
        best_len = 0
        for c in candidates:
            t = self._clean(c.get_text(" ", strip=True))
            if len(t) > best_len:
                best, best_len = t, len(t)
        return best

    def _extract_deadline(self, soup: BeautifulSoup) -> str:
        body_text = soup.get_text(" ", strip=True)
        m = DEADLINE_PAT.search(body_text)
        if m:
            return self._clean(m.group(0))
        return ""
