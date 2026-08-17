"""Ingestion audit trail.

Every file that enters the pipeline is recorded with its source URL, checksum,
row count and processing status. Provenance is a first-class output of this
product, not an afterthought - the dashboard reads from this table to display
where its numbers came from.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

import pandas as pd

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

AUDIT_FILENAME = "ingestion_audit.parquet"


@dataclass
class AuditRecord:
    """One row of the ingestion metadata table."""

    dataset: str
    reporting_period: str
    source_url: str
    source_file: str
    source_page: str
    downloaded_at: str
    bytes_downloaded: int
    checksum_sha256: str | None
    row_count: int
    processing_status: str      # "processed" | "download_failed" | "parse_failed"
    data_source_type: str
    published_date: str | None = None
    source_period_label: str | None = None
    revision: int = 0
    message: str = ""
    ingested_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


class AuditLog:
    """Accumulates audit records and persists them to Parquet."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    def add(self, record: AuditRecord) -> None:
        self._records.append(record)

    def extend(self, records: list[AuditRecord]) -> None:
        self._records.extend(records)

    @property
    def records(self) -> list[AuditRecord]:
        return list(self._records)

    def to_frame(self) -> pd.DataFrame:
        if not self._records:
            return pd.DataFrame(
                columns=[f.name for f in AuditRecord.__dataclass_fields__.values()]
            )
        return pd.DataFrame([asdict(r) for r in self._records])

    def save(self) -> pd.DataFrame:
        settings = get_settings()
        settings.ensure_directories()
        frame = self.to_frame()
        target = settings.processed_dir / AUDIT_FILENAME
        frame.to_parquet(target, index=False)
        logger.info("Wrote ingestion audit (%d records) to %s", len(frame), target)
        return frame

    def summary(self) -> dict:
        frame = self.to_frame()
        if frame.empty:
            return {"files": 0, "processed": 0, "failed": 0, "rows": 0}
        return {
            "files": len(frame),
            "processed": int((frame["processing_status"] == "processed").sum()),
            "failed": int((frame["processing_status"] != "processed").sum()),
            "rows": int(frame["row_count"].sum()),
        }


def load_audit() -> pd.DataFrame:
    """Read the persisted audit table, or an empty frame if absent."""
    path = get_settings().processed_dir / AUDIT_FILENAME
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)
