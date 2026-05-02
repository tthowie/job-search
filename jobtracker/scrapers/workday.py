"""Generic Workday CXS scraper."""

from __future__ import annotations

import logging
from typing import Iterable
from urllib.parse import urljoin, urlparse

from ..storage import Job
from .base import BaseScraper, JobStub
from .generic import GenericScraper

log = logging.getLogger(__name__)


class WorkdayScraper(BaseScraper):
    """Scrape public Workday career sites using the CXS JSON endpoints."""

    def list_jobs(self) -> Iterable[JobStub]:
        stubs = list(self._try_api())
        if stubs:
            return stubs
        return list(GenericScraper(self.site, self.settings).list_jobs())

    def _try_api(self) -> Iterable[JobStub]:
        parsed, tenant, site_path, public_path = self._site_parts()
        if not tenant or not site_path:
            return

        api = f"{parsed.scheme}://{parsed.netloc}/wday/cxs/{tenant}/{site_path}/jobs"
        seen: set[str] = set()
        keywords = self.settings.keywords if self.settings.keywords else [""]
        for keyword in keywords:
            payload = {
                "appliedFacets": {},
                "limit": min(self.settings.max_jobs_per_site, 20),
                "offset": 0,
                "searchText": keyword,
            }
            try:
                response = self.session.post(
                    api,
                    json=payload,
                    timeout=self.REQUEST_TIMEOUT,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("Workday API call failed for %s: %s", self.site.id, e)
                continue
            if response.status_code >= 400:
                log.warning(
                    "Workday API status %s for %s",
                    response.status_code,
                    self.site.id,
                )
                continue
            data = response.json()
            for item in data.get("jobPostings", []):
                external_path = item.get("externalPath") or ""
                if not external_path:
                    continue
                url = urljoin(self.site.url, f"/{public_path}{external_path}")
                if url in seen:
                    continue
                seen.add(url)
                yield JobStub(
                    url=url,
                    title=item.get("title") or "",
                    company=self.site.name,
                    location=item.get("locationsText") or "",
                )

    def fetch_details(self, stub: JobStub) -> Job:
        parsed_site, tenant, site_path, public_path = self._site_parts()
        parsed_job = urlparse(stub.url)
        external_path = parsed_job.path
        for prefix in (f"/{public_path}", f"/{site_path}"):
            if external_path.startswith(prefix):
                external_path = external_path[len(prefix):]
                break
        api_url = (
            f"{parsed_site.scheme}://{parsed_site.netloc}"
            f"/wday/cxs/{tenant}/{site_path}{external_path}"
        )
        data = self.get_json(api_url)
        if not isinstance(data, dict):
            return super().fetch_details(stub)

        info = data.get("jobPostingInfo", {})
        description = self._clean(info.get("jobDescription") or "")
        return Job(
            url=stub.url,
            title=info.get("title") or stub.title,
            company=stub.company or self.site.name,
            description=description,
            qualifications="",
            deadline=info.get("jobPostingSite", {}).get("postingEndDate", ""),
            location=stub.location or info.get("location") or "",
            site_id=self.site.id,
        )

    def _site_parts(self):
        parsed = urlparse(self.site.url)
        tenant = parsed.netloc.split(".", 1)[0]
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) >= 2 and "-" in parts[0]:
            site_path = parts[1]
            public_path = "/".join(parts[:2])
        else:
            site_path = parts[0] if parts else ""
            public_path = site_path
        return parsed, tenant, site_path, public_path
