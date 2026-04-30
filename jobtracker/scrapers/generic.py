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

import re
from typing import Iterable
from urllib.parse import urljoin, urlparse

from .base import BaseScraper, JobStub

JOB_HREF_PAT = re.compile(
    r"/(?:job|jobs|career|careers|position|positions|vacancy|vacancies|opening|openings|opportunity|opportunities|listing|requisition)s?[/\-]",
    re.IGNORECASE,
)


class GenericScraper(BaseScraper):

    def list_jobs(self) -> Iterable[JobStub]:
        soup = self.get_html(self.site.url)
        if soup is None:
            return []
        base_url = self.site.url
        host = urlparse(base_url).netloc

        seen: set[str] = set()
        out: list[JobStub] = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#"):
                continue
            full = urljoin(base_url, href)
            if urlparse(full).netloc != host:
                continue
            if not JOB_HREF_PAT.search(full):
                continue
            if full in seen:
                continue
            seen.add(full)
            title = a.get_text(" ", strip=True)
            # If the anchor text is empty, look for the nearest heading in its
            # ancestor card.
            if not title or len(title) < 4:
                parent = a.find_parent(["li", "div", "article", "tr"])
                if parent:
                    h = parent.find(["h1", "h2", "h3", "h4"])
                    if h:
                        title = h.get_text(" ", strip=True)
            out.append(JobStub(url=full, title=title or "", company=self.site.name))
        return out
