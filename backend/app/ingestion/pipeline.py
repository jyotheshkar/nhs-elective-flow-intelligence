"""End-to-end ingestion pipeline.

    discover -> download -> parse -> validate -> clean -> transform -> persist

Failures are isolated per file: one unreadable month is recorded in the audit
log and skipped, rather than aborting an otherwise successful run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.config import get_settings
from app.ingestion.audit import AuditLog, AuditRecord
from app.ingestion.discovery import DiscoveredFile, discover_files
from app.ingestion.downloader import download_file, make_client
from app.ingestion.rtt_reader import WorkbookSchemaError, read_provider_workbook
from app.transformation.build import (
    build_dim_date,
    build_dim_provider,
    build_dim_specialty,
    build_fact_rtt,
)
from app.transformation.cleaning import clean_frame
from app.transformation.schema import (
    DATA_SOURCE_OFFICIAL,
    DATASET_SPECS,
)
from app.transformation.validation import validate_canonical_fact, validate_raw_frame
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class IngestionResult:
    """Outcome of a full ingestion run."""

    fact: pd.DataFrame
    dim_provider: pd.DataFrame
    dim_specialty: pd.DataFrame
    dim_date: pd.DataFrame
    audit: pd.DataFrame
    validation_passed: bool
    messages: list[str] = field(default_factory=list)


def run_ingestion(
    months: int | None = None,
    force_download: bool = False,
    datasets: list[str] | None = None,
) -> IngestionResult:
    """Ingest official NHS England RTT provider files into the canonical model."""
    settings = get_settings()
    settings.ensure_directories()
    months = months or settings.ingest_months

    logger.info("Starting ingestion for the %d most recent reporting months", months)
    discovered = discover_files(months=months, datasets=datasets)
    if not discovered:
        raise RuntimeError(
            "No source files were discovered. Check network access and the "
            "publication pages listed in config/sources.yaml, or supply a URL "
            "directly with: python scripts/download_data.py --url <URL> "
            "--dataset incomplete"
        )

    audit = AuditLog()
    parsed: dict[str, list[pd.DataFrame]] = {"incomplete": [], "admitted": [],
                                             "non_admitted": []}

    with make_client() as client:
        for item in discovered:
            _ingest_one(item, client, audit, parsed, force_download)

    return _assemble(parsed, audit)


def ingest_local_files(
    files: list[tuple[str, str, pd.Timestamp]],
) -> IngestionResult:
    """Ingest already-downloaded workbooks.

    ``files`` is a list of ``(path, dataset, reporting_month)``. Used by the
    manual ingestion path documented in the README for environments without
    outbound network access.
    """
    from pathlib import Path

    audit = AuditLog()
    parsed: dict[str, list[pd.DataFrame]] = {"incomplete": [], "admitted": [],
                                             "non_admitted": []}
    for path_str, dataset, month in files:
        path = Path(path_str)
        try:
            workbook = read_provider_workbook(path, dataset, pd.Timestamp(month).date())
        except (WorkbookSchemaError, ValueError, OSError) as exc:
            logger.error("Failed to parse %s: %s", path.name, exc)
            audit.add(
                AuditRecord(
                    dataset=dataset,
                    reporting_period=pd.Timestamp(month).strftime("%Y-%m"),
                    source_url="(local file)",
                    source_file=path.name,
                    source_page="(local file)",
                    downloaded_at="",
                    bytes_downloaded=path.stat().st_size if path.exists() else 0,
                    checksum_sha256=None,
                    row_count=0,
                    processing_status="parse_failed",
                    data_source_type=DATA_SOURCE_OFFICIAL,
                    message=str(exc),
                )
            )
            continue

        cleaned = clean_frame(workbook.frame, dataset)
        parsed[dataset].append(cleaned)
        audit.add(
            AuditRecord(
                dataset=dataset,
                reporting_period=pd.Timestamp(month).strftime("%Y-%m"),
                source_url="(local file)",
                source_file=path.name,
                source_page="(local file)",
                downloaded_at="",
                bytes_downloaded=path.stat().st_size,
                checksum_sha256=None,
                row_count=len(cleaned),
                processing_status="processed",
                data_source_type=DATA_SOURCE_OFFICIAL,
                published_date=workbook.metadata.get("published_date"),
                source_period_label=workbook.metadata.get("source_period"),
            )
        )
    return _assemble(parsed, audit)


def _ingest_one(
    item: DiscoveredFile,
    client,
    audit: AuditLog,
    parsed: dict[str, list[pd.DataFrame]],
    force_download: bool,
) -> None:
    """Download, parse, validate and clean a single discovered file."""
    download = download_file(item, client=client, force=force_download)
    if download.status == "failed" or download.local_path is None:
        audit.add(
            AuditRecord(
                dataset=item.dataset,
                reporting_period=item.month_key,
                source_url=item.url,
                source_file=item.filename,
                source_page=item.source_page,
                downloaded_at=download.downloaded_at,
                bytes_downloaded=0,
                checksum_sha256=None,
                row_count=0,
                processing_status="download_failed",
                data_source_type=DATA_SOURCE_OFFICIAL,
                revision=item.revision,
                message=download.message,
            )
        )
        return

    try:
        workbook = read_provider_workbook(
            download.local_path, item.dataset, item.reporting_month
        )
    except (WorkbookSchemaError, ValueError, OSError, KeyError) as exc:
        logger.error("Failed to parse %s: %s", item.filename, exc)
        audit.add(
            AuditRecord(
                dataset=item.dataset,
                reporting_period=item.month_key,
                source_url=item.url,
                source_file=item.filename,
                source_page=item.source_page,
                downloaded_at=download.downloaded_at,
                bytes_downloaded=download.bytes_downloaded,
                checksum_sha256=download.checksum_sha256,
                row_count=0,
                processing_status="parse_failed",
                data_source_type=DATA_SOURCE_OFFICIAL,
                revision=item.revision,
                message=str(exc),
            )
        )
        return

    spec = DATASET_SPECS[item.dataset]
    report = validate_raw_frame(
        workbook.frame,
        dataset=f"{item.dataset} {item.month_key}",
        required_columns=("provider_code", "specialty_code", *spec.required_measures),
    )
    if not report.passed:
        audit.add(
            AuditRecord(
                dataset=item.dataset,
                reporting_period=item.month_key,
                source_url=item.url,
                source_file=item.filename,
                source_page=item.source_page,
                downloaded_at=download.downloaded_at,
                bytes_downloaded=download.bytes_downloaded,
                checksum_sha256=download.checksum_sha256,
                row_count=len(workbook.frame),
                processing_status="validation_failed",
                data_source_type=DATA_SOURCE_OFFICIAL,
                revision=item.revision,
                message="; ".join(i.message for i in report.errors),
            )
        )
        return

    cleaned = clean_frame(workbook.frame, item.dataset)
    parsed[item.dataset].append(cleaned)
    audit.add(
        AuditRecord(
            dataset=item.dataset,
            reporting_period=item.month_key,
            source_url=item.url,
            source_file=item.filename,
            source_page=item.source_page,
            downloaded_at=download.downloaded_at,
            bytes_downloaded=download.bytes_downloaded,
            checksum_sha256=download.checksum_sha256,
            row_count=len(cleaned),
            processing_status="processed",
            data_source_type=DATA_SOURCE_OFFICIAL,
            revision=item.revision,
            published_date=workbook.metadata.get("published_date"),
            source_period_label=workbook.metadata.get("source_period"),
            message=(
                f"{len(report.warnings)} validation warnings"
                if report.warnings
                else ""
            ),
        )
    )


def _assemble(
    parsed: dict[str, list[pd.DataFrame]], audit: AuditLog
) -> IngestionResult:
    """Build the star schema from the accumulated monthly frames."""
    messages: list[str] = []
    if not parsed["incomplete"]:
        raise RuntimeError(
            "No waiting-list (incomplete pathway) files were successfully "
            "processed. Review the ingestion audit log for details."
        )

    incomplete = pd.concat(parsed["incomplete"], ignore_index=True)
    admitted = (
        pd.concat(parsed["admitted"], ignore_index=True)
        if parsed["admitted"]
        else None
    )
    non_admitted = (
        pd.concat(parsed["non_admitted"], ignore_index=True)
        if parsed["non_admitted"]
        else None
    )

    if admitted is None:
        messages.append(
            "No admitted-activity files were processed; activity-derived "
            "metrics and scenarios will be unavailable."
        )
    if non_admitted is None:
        messages.append(
            "No non-admitted-activity files were processed; completed activity "
            "will understate total throughput."
        )

    all_frames = [f for f in (incomplete, admitted, non_admitted) if f is not None]
    dim_provider = build_dim_provider(all_frames)
    dim_specialty = build_dim_specialty(all_frames)
    fact = build_fact_rtt(incomplete, admitted, non_admitted, DATA_SOURCE_OFFICIAL)
    dim_date = build_dim_date(list(fact["reporting_month"].unique()))

    report = validate_canonical_fact(fact)
    if not report.passed:
        messages.extend(i.message for i in report.errors)

    logger.info(
        "Ingestion complete: %d fact rows, %d providers, %d specialties, "
        "%d reporting months",
        len(fact), len(dim_provider), len(dim_specialty), len(dim_date),
    )
    return IngestionResult(
        fact=fact,
        dim_provider=dim_provider,
        dim_specialty=dim_specialty,
        dim_date=dim_date,
        audit=audit.save(),
        validation_passed=report.passed,
        messages=messages,
    )
