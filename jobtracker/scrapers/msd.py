"""MSD UK careers (jobs.msd.com) — Phenom platform.

Same overall approach as the Sanofi scraper: try the Phenom JSON API, fall
back to HTML.
"""

from __future__ import annotations

from typing import Iterable
from urllib.parse import urljoin, urlencode, urlparse

from .base import BaseScraper, JobStub
from .generic import GenericScraper


class MSDScraper(BaseScraper):
    BASE = "https://jobs.msd.com"
    API = "https://jobs.msd.com/api/jobs"

    def list_jobs(self) -> Iterable[JobStub]:
        stubs = list(self._try_api())
        if stubs:
            return stubs
        return list(self._try_html())

    def _try_api(self) -> Iterable[JobStub]:
        keyword = " ".join(self.settings.keywords[:3]) if self.settings.keywords else ""
        params = {
            "from": 0,
            "size": min(self.settings.max_jobs_per_site, 50),
            "keyword": keyword,
            "location": self.settings.location or "United Kingdom",
            "country": "United Kingdom",
            "locale": "en_GB",
        }
        data = self.get_json(f"{self.API}?{urlencode(params)}")
        if not isinstance(data, dict):
            return
        jobs = data.get("jobs") or data.get("hits") or []
        for j in jobs:
            url = j.get("applyUrl") or j.get("url") or j.get("jobUrl") or ""
            if url and not url.startswith("http"):
                url = urljoin(self.BASE, url)
            title = j.get("title") or j.get("jobTitle") or ""
            location = j.get("city") or j.get("location") or j.get("country") or ""
            if url:
                yield JobStub(url=url, title=title, company="MSD", location=location)

    def _try_html(self) -> Iterable[JobStub]:
        soup = self.get_html(self.site.url)
        if soup is None:
            return
        seen: set[str] = set()
        host = urlparse(self.BASE).netloc
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/job/" not in href and "/jobs/" not in href:
                continue
            full = urljoin(self.BASE, href)
            if urlparse(full).netloc != host:
                continue
            if full in seen:
                continue
            seen.add(full)
            title = a.get_text(" ", strip=True)
            if not title:
                parent = a.find_parent(["li", "article", "div"])
                if parent:
                    h = parent.find(["h2", "h3", "h4"])
                    if h:
                        title = h.get_text(" ", strip=True)
            yield JobStub(url=full, title=title, company="MSD")
        if not seen:
            yield from GenericScraper(self.site, self.settings).list_jobs()
