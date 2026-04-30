"""CSV storage for fetched and kept jobs.

We deliberately keep two files:

- ``data/fetched.csv`` — every job we've ever pulled from a site, with a
  ``reviewed`` column. Append-only, deduped by ``url``.
- ``data/kept.csv``    — jobs the user marked "keep" during review, with an
  ``applied`` column. Updates in place when toggling applied.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, asdict, field, fields
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .config import FETCHED_CSV, KEPT_CSV, DATA_DIR


# ---------------------------------------------------------------------------
# Job model
# ---------------------------------------------------------------------------

@dataclass
class Job:
    url: str
    title: str = ""
    company: str = ""
    description: str = ""
    qualifications: str = ""
    deadline: str = ""
    location: str = ""
    site_id: str = ""           # which configured site it came from
    fetched_at: str = ""        # ISO timestamp
    reviewed: bool = False      # only used in fetched.csv
    kept: bool = False          # only used in fetched.csv
    applied: bool = False       # only used in kept.csv

    @classmethod
    def csv_columns(cls) -> list[str]:
        return [f.name for f in fields(cls)]

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "Job":
        kwargs: dict[str, object] = {}
        bool_fields = {"reviewed", "kept", "applied"}
        for f in fields(cls):
            v = row.get(f.name, "")
            if f.name in bool_fields:
                kwargs[f.name] = str(v).strip().lower() in {"true", "1", "yes"}
            else:
                kwargs[f.name] = v or ""
        return cls(**kwargs)  # type: ignore[arg-type]

    def to_row(self) -> dict[str, str]:
        d = asdict(self)
        return {k: ("true" if isinstance(v, bool) and v
                    else "false" if isinstance(v, bool)
                    else str(v)) for k, v in d.items()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_file(path: Path) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=Job.csv_columns())
            writer.writeheader()


def _read_all(path: Path) -> list[Job]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [Job.from_row(row) for row in reader]


def _write_all(path: Path, jobs: Iterable[Job]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=Job.csv_columns())
        writer.writeheader()
        for j in jobs:
            writer.writerow(j.to_row())


# ---------------------------------------------------------------------------
# Public API — fetched.csv
# ---------------------------------------------------------------------------

def known_urls() -> set[str]:
    """URLs already present in fetched.csv (used to dedupe)."""
    _ensure_file(FETCHED_CSV)
    return {j.url for j in _read_all(FETCHED_CSV) if j.url}


def append_fetched(jobs: list[Job]) -> int:
    """Append new jobs to fetched.csv, skipping any with URLs we already have.

    Returns the number actually appended.
    """
    _ensure_file(FETCHED_CSV)
    existing = known_urls()
    fresh: list[Job] = []
    seen_in_batch: set[str] = set()
    now = datetime.utcnow().isoformat(timespec="seconds")
    for j in jobs:
        if not j.url or j.url in existing or j.url in seen_in_batch:
            continue
        if not j.fetched_at:
            j.fetched_at = now
        seen_in_batch.add(j.url)
        fresh.append(j)
    if not fresh:
        return 0
    with FETCHED_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=Job.csv_columns())
        for j in fresh:
            writer.writerow(j.to_row())
    return len(fresh)


def list_fetched() -> list[Job]:
    _ensure_file(FETCHED_CSV)
    return _read_all(FETCHED_CSV)


def list_unreviewed() -> list[Job]:
    return [j for j in list_fetched() if not j.reviewed]


def mark_reviewed(url: str, *, kept: bool) -> None:
    """Mark a fetched job as reviewed. ``kept`` records whether the user kept it."""
    jobs = list_fetched()
    for j in jobs:
        if j.url == url:
            j.reviewed = True
            j.kept = kept
            break
    _write_all(FETCHED_CSV, jobs)


# ---------------------------------------------------------------------------
# Public API — kept.csv
# ---------------------------------------------------------------------------

def list_kept() -> list[Job]:
    _ensure_file(KEPT_CSV)
    return _read_all(KEPT_CSV)


def add_kept(job: Job) -> None:
    _ensure_file(KEPT_CSV)
    kept = list_kept()
    if any(j.url == job.url for j in kept):
        return
    job.applied = False
    kept.append(job)
    _write_all(KEPT_CSV, kept)


def set_applied(url: str, applied: bool) -> None:
    kept = list_kept()
    for j in kept:
        if j.url == url:
            j.applied = applied
            break
    _write_all(KEPT_CSV, kept)
