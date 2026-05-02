"""Generic best-effort scraper.

Strategy:
1. GET the configured search URL.
2. Find anchors whose href looks like a job posting (``/job/``, ``/jobs/``,
   ``/careers/``, ``/positions/``, ``/vacancy/``, etc.) and whose link text or
   surrounding card looks like a title.
3. For each, follow the link and use base.fetch_details to pull description,
   qualifications, and deadline.
"""

from __future__ import annotations

import json
import re
from typing import Iterable
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup

from .base import BaseScraper, JobStub

JOB_HREF_PAT = re.compile(
    r"/(?:job|jobs|career|careers|position|positions|vacancy|vacancies|opening|openings|opportunity|opportunities|listing|requisition)s?[/\-]",
    re.IGNORECASE,
)


UK_LOCATION_PAT = re.compile(
    r"\b(united kingdom|uk|england|scotland|wales|northern ireland|"
    r"london|manchester|birmingham|glasgow|edinburgh|leeds|reading|"
    r"slough|maidenhead|high wycombe|surrey|berkshire)\b",
    re.IGNORECASE,
)

NON_UK_LOCATION_PAT = re.compile(
    r"\b(united states|usa|us|sweden|japan|brazil|canada|taiwan|"
    r"india|france|germany|italy|spain|netherlands|belgium|switzerland|"
    r"australia|china|singapore|korea|mumbai|hyderabad|delhi|tokyo|osaka|"
    r"gothenburg|sao paulo|boston|lexington|philadelphia|orlando|"
    r"chicago|california|new york|toronto|vancouver|turkey|istanbul|"
    r"louisiana|georgia|mississippi|alabama|tennessee|tennesee|"
    r"ny|ct|pa|oh|mi|ma|ca|tx|nj|fl|ga|la|ms|al)\b",
    re.IGNORECASE,
)


class GenericScraper(BaseScraper):

    def list_jobs(self) -> Iterable[JobStub]:
        seen: set[str] = set()
        out: list[JobStub] = []
        for search_url in self._search_urls():
            out.extend(self._list_jobs_from_url(search_url, seen))
        return out

    def _search_urls(self) -> list[str]:
        if "{keyword}" not in self.site.url:
            return [self.site.url]
        keywords = [k for k in self.settings.keywords if k.strip()]
        if not keywords:
            return [self.site.url.replace("{keyword}", "")]
        return [
            self.site.url.replace("{keyword}", quote_plus(keyword))
            for keyword in keywords
        ]

    def _list_jobs_from_url(
        self,
        search_url: str,
        seen: set[str],
    ) -> list[JobStub]:
        response = self.get(search_url)
        if response is None:
            return []
        soup = BeautifulSoup(response.text, "lxml")
        host = urlparse(search_url).netloc

        out: list[JobStub] = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#"):
                continue
            full = urljoin(search_url, href)
            if urlparse(full).netloc != host:
                continue
            if not JOB_HREF_PAT.search(full):
                continue
            if self._is_listing_url(full):
                continue
            if full in seen:
                continue
            seen.add(full)
            title = a.get_text(" ", strip=True)
            # If the anchor text is empty, look for the nearest heading in its
            # ancestor card.
            parent = a.find_parent(["li", "div", "article", "tr"])
            card_text = ""
            if parent:
                card_text = parent.get_text(" ", strip=True)
            if not title or len(title) < 4:
                if parent:
                    h = parent.find(["h1", "h2", "h3", "h4"])
                    if h:
                        title = h.get_text(" ", strip=True)
            location = self._extract_location_hint(" ".join([title, card_text]))
            out.append(
                JobStub(
                    url=full,
                    title=title or "",
                    company=self.site.name,
                    location=location,
                )
            )
        out.extend(self._embedded_job_stubs(response.text, search_url, seen))
        return out

    @staticmethod
    def _is_listing_url(url: str) -> bool:
        path = urlparse(url).path.rstrip("/").lower()
        return path.endswith("/jobs") or path.endswith("/careers")

    def _embedded_job_stubs(
        self,
        page_text: str,
        search_url: str,
        seen: set[str],
    ) -> list[JobStub]:
        out: list[JobStub] = []
        for match in re.finditer(r'"jobSeqNo"', page_text):
            raw_obj = self._json_object_around(page_text, match.start())
            if not raw_obj:
                continue
            try:
                item = json.loads(raw_obj)
            except json.JSONDecodeError:
                continue
            title = item.get("title") or ""
            job_seq = item.get("jobSeqNo") or item.get("jobId") or ""
            if not title or not job_seq:
                continue
            url = self._embedded_job_url(item, search_url)
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(
                JobStub(
                    url=url,
                    title=title,
                    company=self.site.name,
                    location=self._embedded_location(item),
                )
            )
        return out

    @staticmethod
    def _json_object_around(text: str, index: int) -> str:
        start = text.rfind("{", 0, index)
        if start < 0:
            return ""
        depth = 0
        in_string = False
        escape = False
        for pos in range(start, len(text)):
            char = text[pos]
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : pos + 1]
        return ""

    @staticmethod
    def _embedded_job_url(item: dict, search_url: str) -> str:
        for key in ("url", "jobUrl", "applyUrl"):
            url = item.get(key)
            if url:
                return urljoin(search_url, url)
        job_seq = item.get("jobSeqNo") or item.get("jobId") or ""
        title = item.get("title") or "job"
        if not job_seq:
            return ""
        parsed = urlparse(search_url)
        base_path = parsed.path.split("/search-results", 1)[0].rstrip("/")
        slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")
        return urljoin(search_url, f"{base_path}/job/{job_seq}/{slug}")

    @staticmethod
    def _embedded_location(item: dict) -> str:
        location = item.get("location") or item.get("cityStateCountry") or ""
        if location:
            return location
        multi_location = item.get("multi_location") or []
        if isinstance(multi_location, list):
            return "; ".join(str(x) for x in multi_location)
        return str(multi_location)

    def fetch_details(self, stub: JobStub):
        job = super().fetch_details(stub)
        if not job.location:
            job.location = self._extract_location_hint(
                " ".join([job.title, job.description[:500]])
            )
        return job

    @staticmethod
    def _extract_location_hint(text: str) -> str:
        if UK_LOCATION_PAT.search(text or ""):
            return "United Kingdom"
        match = NON_UK_LOCATION_PAT.search(text or "")
        if match:
            return match.group(0)
        return ""
