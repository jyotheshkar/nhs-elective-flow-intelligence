"""Discovery of official NHS England RTT source files.

NHS England publishes each month's provider-level workbooks on a financial-year
page, with filenames that carry a random suffix and, when a month is restated,
a ``-revised`` / ``-revised-2`` marker. Filenames therefore cannot be
constructed - they must be discovered.

This module scrapes the configured publication pages, parses the reporting
month out of each filename, resolves revisions, and returns a deterministic
list of candidate downloads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import httpx
from bs4 import BeautifulSoup

from app.config import get_source_config
from app.utils.logging import get_logger

logger = get_logger(__name__)

_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_REVISION_RE = re.compile(r"revised(?:-(\d+))?", re.IGNORECASE)


@dataclass(frozen=True)
class DiscoveredFile:
    """One candidate source file located on a publication page."""

    dataset: str          # "incomplete" | "admitted" | "non_admitted"
    reporting_month: date  # first day of the reporting month
    url: str
    filename: str
    revision: int          # 0 = original publication, higher = later restatement
    source_page: str

    @property
    def month_key(self) -> str:
        return self.reporting_month.strftime("%Y-%m")


def _parse_revision(filename: str) -> int:
    """Return the revision number encoded in a filename (0 when original)."""
    match = _REVISION_RE.search(filename)
    if not match:
        return 0
    return int(match.group(1)) if match.group(1) else 1


def _parse_reporting_month(mon: str, yy: str) -> date | None:
    """Convert ``("Dec", "25")`` into ``date(2025, 12, 1)``."""
    month = _MONTH_ABBR.get(mon.lower())
    if month is None:
        return None
    year = 2000 + int(yy)
    return date(year, month, 1)


def _extract_links(html: str, page_url: str) -> list[tuple[str, str]]:
    """Return ``(absolute_url, filename)`` for every spreadsheet link found."""
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if not href.lower().endswith((".xlsx", ".xls", ".csv", ".zip")):
            continue
        url = httpx.URL(page_url).join(href)
        results.append((str(url), url.path.rsplit("/", 1)[-1]))
    return results


def discover_files(
    months: int,
    datasets: list[str] | None = None,
    client: httpx.Client | None = None,
) -> list[DiscoveredFile]:
    """Discover the most recent ``months`` reporting periods of provider files.

    Walks the configured publication pages newest-first, collecting candidate
    files until enough distinct reporting months have been found for the
    *required* datasets. Where a month appears more than once, the highest
    revision wins.
    """
    config = get_source_config()
    rtt = config["sources"]["rtt"]
    ingestion_cfg = config.get("ingestion", {})
    wanted = datasets or list(rtt["datasets"].keys())

    patterns = {
        key: re.compile(spec["filename_pattern"], re.IGNORECASE)
        for key, spec in rtt["datasets"].items()
        if key in wanted
    }
    required_datasets = [
        key for key, spec in rtt["datasets"].items()
        if key in wanted and spec.get("required", False)
    ]

    owns_client = client is None
    client = client or httpx.Client(
        timeout=ingestion_cfg.get("request_timeout_seconds", 300),
        headers={"User-Agent": ingestion_cfg.get("user_agent", "nhs-eff/1.0")},
        follow_redirects=True,
    )

    # (dataset, month_key) -> best DiscoveredFile so far
    best: dict[tuple[str, str], DiscoveredFile] = {}
    try:
        for page in rtt["publication_pages"]:
            # Stop early once the required datasets have enough months.
            if _required_months_covered(best, required_datasets, months):
                logger.info("Discovery target met; skipping remaining pages")
                break
            logger.info("Scanning publication page: %s", page)
            try:
                response = client.get(page)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Could not read publication page %s: %s", page, exc)
                continue

            for url, filename in _extract_links(response.text, page):
                for dataset, pattern in patterns.items():
                    match = pattern.match(filename)
                    if not match:
                        continue
                    month = _parse_reporting_month(
                        match.group("mon"), match.group("yy")
                    )
                    if month is None:
                        logger.debug("Unparseable reporting month in %s", filename)
                        continue
                    candidate = DiscoveredFile(
                        dataset=dataset,
                        reporting_month=month,
                        url=url,
                        filename=filename,
                        revision=_parse_revision(filename),
                        source_page=page,
                    )
                    key = (dataset, candidate.month_key)
                    incumbent = best.get(key)
                    if incumbent is None or candidate.revision > incumbent.revision:
                        best[key] = candidate
                    break
    finally:
        if owns_client:
            client.close()

    selected = _select_recent_months(best, required_datasets, months)
    logger.info(
        "Discovered %d files across %d reporting months",
        len(selected),
        len({f.month_key for f in selected}),
    )
    return selected


def _months_for(
    best: dict[tuple[str, str], DiscoveredFile], dataset: str
) -> set[str]:
    return {month for (ds, month) in best if ds == dataset}


def _required_months_covered(
    best: dict[tuple[str, str], DiscoveredFile],
    required_datasets: list[str],
    months: int,
) -> bool:
    if not required_datasets:
        return False
    return all(len(_months_for(best, ds)) >= months for ds in required_datasets)


def _select_recent_months(
    best: dict[tuple[str, str], DiscoveredFile],
    required_datasets: list[str],
    months: int,
) -> list[DiscoveredFile]:
    """Keep only the ``months`` most recent reporting periods.

    The window is anchored on the *required* datasets (the waiting list), so an
    activity file without a matching waiting-list month is dropped rather than
    widening the window.
    """
    if not best:
        return []
    anchor = required_datasets[0] if required_datasets else next(iter(best))[0]
    anchor_months = sorted(_months_for(best, anchor), reverse=True)[:months]
    if not anchor_months:
        anchor_months = sorted({m for _, m in best}, reverse=True)[:months]
    keep = set(anchor_months)
    return sorted(
        (f for (ds, month), f in best.items() if month in keep),
        key=lambda f: (f.reporting_month, f.dataset),
    )
