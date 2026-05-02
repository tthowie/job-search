"""MSD UK careers (jobs.msd.com) — Phenom platform.

Same overall approach as the Sanofi scraper: try the Phenom JSON API, fall
back to HTML.
"""

from __future__ import annotations

import json
from typing import Iterable
from urllib.parse import urljoin, urlencode, urlparse

from bs4 import BeautifulSoup

from .base import BaseScraper, JobStub
from .generic import GenericScraper
from ..storage import Job


class MSDScraper(BaseScraper):
    BASE = "https://jobs.msd.com"
    API = "https://jobs.msd.com/api/jobs"

    def list_jobs(self) -> Iterable[JobStub]:
        stubs = list(self._try_html())
        if stubs:
            return stubs
        return list(self._try_api())

    def _try_api(self) -> Iterable[JobStub]:
        seen: set[str] = set()
        keywords = self.settings.keywords if self.settings.keywords else [""]
        for keyword in keywords:
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
                continue
            jobs = data.get("jobs") or data.get("hits") or []
            for j in jobs:
                url = j.get("applyUrl") or j.get("url") or j.get("jobUrl") or ""
                if url and not url.startswith("http"):
                    url = urljoin(self.BASE, url)
                if not url or url in seen:
                    continue
                seen.add(url)
                title = j.get("title") or j.get("jobTitle") or ""
                location = j.get("city") or j.get("location") or j.get("country") or ""
                yield JobStub(url=url, title=title, company="MSD", location=location)

    def _try_html(self) -> Iterable[JobStub]:
        soup = self.get_html(self.site.url)
        if soup is None:
            return
        embedded_jobs = list(self._embedded_search_jobs(soup))
        if embedded_jobs:
            yield from embedded_jobs
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

    def _embedded_search_jobs(self, soup) -> Iterable[JobStub]:
        seen: set[str] = set()
        for script in soup.find_all("script"):
            text = script.string or script.get_text()
            marker = "phApp.ddo = "
            start = text.find(marker)
            if start == -1:
                continue
            payload = text[start + len(marker):]
            try:
                ddo, _ = json.JSONDecoder().raw_decode(payload)
            except json.JSONDecodeError:
                continue
            search = ddo.get("eagerLoadRefineSearch", {})
            jobs = search.get("data", {}).get("jobs", [])
            for j in jobs:
                url = (
                    j.get("jobUrl")
                    or j.get("url")
                    or j.get("seoJobUrl")
                    or j.get("applyUrl")
                    or ""
                )
                if url and not url.startswith("http"):
                    url = urljoin(self.BASE, url)
                if not url or url in seen:
                    continue
                seen.add(url)
                title = j.get("title") or j.get("jobTitle") or ""
                location = (
                    "; ".join(j.get("multi_location", []))
                    or j.get("location")
                    or j.get("cityStateCountry")
                    or j.get("country")
                    or ""
                )
                filter_title = " ".join([
                    title,
                    j.get("descriptionTeaser") or "",
                    j.get("category") or "",
                    " ".join(j.get("ml_skills", [])),
                ])
                yield JobStub(
                    url=url,
                    title=filter_title,
                    company="MSD",
                    location=location,
                )

    def fetch_details(self, stub: JobStub) -> Job:
        parsed = urlparse(stub.url)
        path = parsed.path.removesuffix("/apply")
        if "/SearchJobs/" in path:
            path = path.split("/SearchJobs/", 1)[1]
        api_url = f"https://msd.wd5.myworkdayjobs.com/wday/cxs/msd/SearchJobs/{path}"
        data = self.get_json(api_url, headers={"Accept": "application/json"})
        if not isinstance(data, dict):
            return super().fetch_details(stub)

        info = data.get("jobPostingInfo", {})
        description_html = info.get("jobDescription") or ""
        description = BeautifulSoup(description_html, "lxml").get_text(" ", strip=True)
        location = "; ".join(
            part for part in [
                info.get("location") or info.get("locationsText") or "",
                stub.location,
            ]
            if part
        )
        return Job(
            url=stub.url,
            title=info.get("title") or stub.title,
            company=stub.company or self.site.name,
            description=self._clean(description),
            qualifications="",
            deadline=info.get("jobPostingSite", {}).get("postingEndDate", ""),
            location=location,
            site_id=self.site.id,
        )
