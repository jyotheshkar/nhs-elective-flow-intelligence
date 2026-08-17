"""Download official source files with retry, caching and audit metadata."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.config import get_settings, get_source_config
from app.ingestion.discovery import DiscoveredFile
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DownloadResult:
    """Outcome of one download attempt, recorded in the ingestion audit log."""

    dataset: str
    reporting_month: str
    source_url: str
    source_file: str
    local_path: Path | None
    downloaded_at: str
    bytes_downloaded: int
    checksum_sha256: str | None
    status: str            # "downloaded" | "cached" | "failed"
    message: str = ""


def _sha256(path: Path) -> str:
    """Checksum a file in chunks so large workbooks do not load into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(
    discovered: DiscoveredFile,
    client: httpx.Client,
    force: bool = False,
) -> DownloadResult:
    """Download one discovered file into ``data/raw``, reusing a valid cache."""
    settings = get_settings()
    settings.ensure_directories()
    target_dir = settings.raw_dir / discovered.dataset
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / discovered.filename
    now = datetime.now(UTC).isoformat()

    if target.exists() and target.stat().st_size > 0 and not force:
        logger.info("Cached: %s", discovered.filename)
        return DownloadResult(
            dataset=discovered.dataset,
            reporting_month=discovered.month_key,
            source_url=discovered.url,
            source_file=discovered.filename,
            local_path=target,
            downloaded_at=datetime.fromtimestamp(
                target.stat().st_mtime, tz=UTC
            ).isoformat(),
            bytes_downloaded=target.stat().st_size,
            checksum_sha256=_sha256(target),
            status="cached",
        )

    max_retries = get_source_config().get("ingestion", {}).get("max_retries", 3)
    last_error = ""
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "Downloading %s (attempt %d/%d)",
                discovered.filename, attempt, max_retries,
            )
            # Stream to disk: the incomplete-pathway workbooks are ~10 MB each.
            with client.stream("GET", discovered.url) as response:
                response.raise_for_status()
                tmp = target.with_suffix(target.suffix + ".part")
                with tmp.open("wb") as fh:
                    for chunk in response.iter_bytes(chunk_size=512 * 1024):
                        fh.write(chunk)
            tmp.replace(target)
            size = target.stat().st_size
            return DownloadResult(
                dataset=discovered.dataset,
                reporting_month=discovered.month_key,
                source_url=discovered.url,
                source_file=discovered.filename,
                local_path=target,
                downloaded_at=now,
                bytes_downloaded=size,
                checksum_sha256=_sha256(target),
                status="downloaded",
            )
        except (httpx.HTTPError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Download failed (%s): %s", discovered.filename, last_error)

    return DownloadResult(
        dataset=discovered.dataset,
        reporting_month=discovered.month_key,
        source_url=discovered.url,
        source_file=discovered.filename,
        local_path=None,
        downloaded_at=now,
        bytes_downloaded=0,
        checksum_sha256=None,
        status="failed",
        message=last_error,
    )


def download_from_url(url: str, dataset: str, client: httpx.Client) -> DownloadResult:
    """Deterministic fallback path: download an explicitly supplied URL.

    Used by ``scripts/download_data.py --url`` when automatic discovery cannot
    resolve a publication page.
    """
    import re

    from app.ingestion.discovery import (
        _parse_reporting_month,
        _parse_revision,
    )

    filename = httpx.URL(url).path.rsplit("/", 1)[-1]
    month_match = re.search(r"([A-Za-z]{3})(\d{2})", filename)
    month = None
    if month_match:
        month = _parse_reporting_month(month_match.group(1), month_match.group(2))
    if month is None:
        raise ValueError(
            f"Could not infer a reporting month from filename '{filename}'. "
            "Expected a 'MonYY' fragment such as 'Dec25'."
        )
    discovered = DiscoveredFile(
        dataset=dataset,
        reporting_month=month,
        url=url,
        filename=filename,
        revision=_parse_revision(filename),
        source_page="(supplied directly)",
    )
    return download_file(discovered, client=client)


def make_client() -> httpx.Client:
    """Build an HTTP client configured from ``config/sources.yaml``."""
    cfg = get_source_config().get("ingestion", {})
    return httpx.Client(
        timeout=cfg.get("request_timeout_seconds", 300),
        headers={"User-Agent": cfg.get("user_agent", "nhs-eff/1.0")},
        follow_redirects=True,
    )
