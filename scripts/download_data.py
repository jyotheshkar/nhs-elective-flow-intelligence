"""Download official NHS England RTT provider files.

Usage
-----
Automatic discovery (default)::

    python scripts/download_data.py --months 18

Deterministic fallback when discovery cannot resolve a publication page::

    python scripts/download_data.py \
        --url "https://www.england.nhs.uk/.../Incomplete-Provider-Dec25-....xlsx" \
        --dataset incomplete

List what discovery finds without downloading anything::

    python scripts/download_data.py --dry-run
"""

from __future__ import annotations

import argparse
import sys

import _bootstrap  # noqa: F401  (import for its side effect)

from app.config import get_settings, get_source_config
from app.ingestion.discovery import discover_files
from app.ingestion.downloader import download_from_url, make_client
from app.utils.logging import configure_logging, get_logger

logger = get_logger("scripts.download_data")


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--months",
        type=int,
        default=settings.ingest_months,
        help="Number of most recent reporting months to download.",
    )
    parser.add_argument(
        "--url",
        help="Download this exact file instead of running discovery.",
    )
    parser.add_argument(
        "--dataset",
        choices=["incomplete", "admitted", "non_admitted"],
        default="incomplete",
        help="Dataset the --url file belongs to.",
    )
    parser.add_argument(
        "--datasets",
        nargs="*",
        choices=["incomplete", "admitted", "non_admitted"],
        help="Restrict discovery to these datasets.",
    )
    parser.add_argument("--force", action="store_true", help="Re-download cached files.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List discovered files without downloading.",
    )
    args = parser.parse_args()

    max_months = get_source_config().get("ingestion", {}).get("max_months", 36)
    months = max(1, min(args.months, max_months))

    if args.url:
        with make_client() as client:
            result = download_from_url(args.url, args.dataset, client)
        logger.info(
            "%s: %s (%s bytes)",
            result.status, result.source_file, f"{result.bytes_downloaded:,}",
        )
        return 0 if result.status != "failed" else 1

    discovered = discover_files(months=months, datasets=args.datasets)
    if not discovered:
        logger.error(
            "No files discovered. Check network access, or supply --url directly."
        )
        return 1

    logger.info("Discovered %d files:", len(discovered))
    for item in discovered:
        logger.info("  [%s] %s -> %s", item.month_key, item.dataset, item.filename)

    if args.dry_run:
        return 0

    from app.ingestion.downloader import download_file  # noqa: PLC0415

    failures = 0
    with make_client() as client:
        for item in discovered:
            result = download_file(item, client=client, force=args.force)
            if result.status == "failed":
                failures += 1
                logger.error("FAILED %s: %s", item.filename, result.message)

    logger.info(
        "Download complete: %d succeeded, %d failed",
        len(discovered) - failures, failures,
    )
    return 1 if failures == len(discovered) else 0


if __name__ == "__main__":
    sys.exit(main())
