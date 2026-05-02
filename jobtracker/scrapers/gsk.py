"""GSK careers — Workday-backed.

GSK's careers site (www.gsk.com/en-gb/careers/search-jobs/) embeds a Workday
job search. The reliable data source is the Workday CXS JSON endpoint:

    POST https://gsk.wd5.myworkdayjobs.com/wday/cxs/gsk/GSKCareers/jobs

with a JSON body like::

    {"appliedFacets": {}, "limit": 20, "offset": 0,
     "searchText": "medical science liaison"}

We try that first; if it fails (because GSK changed tenants or paths) we fall
back to scraping anchors from the public search page.
"""

from __future__ import annotations

import logging
from typing import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import BaseScraper, JobStub
from .generic import GenericScraper
from ..storage import Job

log = logging.getLogger(__name__)


class GSKScraper(BaseScraper):
    BASE = "https://gsk.wd5.myworkdayjobs.com"
    API = "https://gsk.wd5.myworkdayjobs.com/wday/cxs/gsk/GSKCareers/jobs"
    PUBLIC_BASE = "https://gsk.wd5.myworkdayjobs.com/GSKCareers"

    def list_jobs(self) -> Iterable[JobStub]:
        stubs = list(self._try_workday_api())
        if stubs:
            return stubs
        return list(self._try_html())

    def _try_workday_api(self) -> Iterable[JobStub]:
        seen: set[str] = set()
        keywords = self.settings.keywords if self.settings.keywords else [""]
        for keyword in keywords:
            body = {
                "appliedFacets": {},
                "limit": min(self.settings.max_jobs_per_site, 20),
                "offset": 0,
                "searchText": keyword,
            }
            try:
                r = self.session.post(
                    self.API,
                    json=body,
                    timeout=self.REQUEST_TIMEOUT,
                    headers={
                        "Accept": "application/json",
                        "Origin": self.BASE,
                        "Referer": self.PUBLIC_BASE,
                    },
                )
            except Exception as e:  # noqa: BLE001
                log.warning("GSK Workday API call failed: %s", e)
                continue
            if r.status_code >= 400:
                log.warning("GSK Workday API status %s", r.status_code)
                continue
            try:
                data = r.json()
            except ValueError:
                continue
            postings = data.get("jobPostings", [])
            for p in postings:
                external_path = p.get("externalPath") or ""
                url = urljoin(
                    f"{self.PUBLIC_BASE}/",
                    external_path.lstrip("/"),
                ) if external_path else ""
                if not url or url in seen:
                    continue
                seen.add(url)
                title = p.get("title", "")
                location = p.get("locationsText", "")
                if "location" in location.lower():
                    location = ""
                filter_title = " ".join(part for part in [title, keyword] if part)
                yield JobStub(
                    url=url,
                    title=filter_title,
                    company="GSK",
                    location=location,
                )

    def fetch_details(self, stub: JobStub) -> Job:
        external_path = urlparse(stub.url).path
        prefix = "/GSKCareers"
        if external_path.startswith(prefix):
            external_path = external_path[len(prefix):]
        api_url = f"{self.API.removesuffix('/jobs')}{external_path}"
        data = self.get_json(api_url, headers={"Accept": "application/json"})
        if not isinstance(data, dict):
            return super().fetch_details(stub)

        info = data.get("jobPostingInfo", {})
        description_html = info.get("jobDescription") or ""
        description = BeautifulSoup(description_html, "lxml").get_text(" ", strip=True)
        location = info.get("location") or info.get("locationsText") or stub.location
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

    def _try_html(self) -> Iterable[JobStub]:
        soup = self.get_html(self.site.url)
        if soup is None:
            return
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full = urljoin(self.site.url, href)
            host = urlparse(full).netloc
            if "myworkdayjobs.com" not in host and "gsk.com" not in host:
                continue
            if not any(seg in full for seg in ("/job/", "/job-detail", "/details/", "/JobDetail")):
                continue
            if full in seen:
                continue
            seen.add(full)
            title = a.get_text(" ", strip=True)
            yield JobStub(url=full, title=title, company="GSK")
        if not seen:
            yield from GenericScraper(self.site, self.settings).list_jobs()
