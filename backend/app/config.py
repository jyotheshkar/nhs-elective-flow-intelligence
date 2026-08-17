"""Application configuration.

Centralises every path, tunable and feature flag. Nothing else in the codebase
should read environment variables directly.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings, overridable via environment variables or a .env file."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Identity -----------------------------------------------------------
    app_name: str = "NHS Elective Flow Intelligence"
    app_version: str = "1.0.0"

    # --- Data mode ----------------------------------------------------------
    # "official" -> ingested NHS England public statistics
    # "demo"     -> clearly-labelled synthetic data for demonstration only
    app_data_mode: Literal["official", "demo"] = "official"

    # --- Paths --------------------------------------------------------------
    repo_root: Path = REPO_ROOT
    data_dir: Path = REPO_ROOT / "data"
    raw_dir: Path = REPO_ROOT / "data" / "raw"
    processed_dir: Path = REPO_ROOT / "data" / "processed"
    sample_dir: Path = REPO_ROOT / "data" / "sample"
    sources_config_path: Path = REPO_ROOT / "config" / "sources.yaml"

    # --- Ingestion ----------------------------------------------------------
    ingest_months: int = 18

    # --- Analytics tunables -------------------------------------------------
    # Provider x specialty series smaller than this are excluded from ranking:
    # tiny lists produce unstable percentage growth and dominate rankings for
    # the wrong reasons. Documented in docs/methodology.md.
    min_waiting_list_for_ranking: int = 200

    # Minimum monthly observations required before a forecast is attempted.
    min_history_for_forecast: int = 6

    # 18-week benchmark used for the performance-gap component of the priority
    # score. This is the operational standard referenced in the NHS
    # Constitution; it is applied as a *benchmark*, not a claim about any
    # individual organisation's contractual target.
    referral_to_treatment_benchmark: float = 92.0

    # --- API ----------------------------------------------------------------
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Optional LLM briefing (disabled unless a key is supplied) ----------
    anthropic_api_key: str | None = None
    llm_briefing_enabled: bool = False
    llm_model: str = "claude-sonnet-5"

    # --- Logging ------------------------------------------------------------
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def warehouse_path(self) -> Path:
        """Location of the DuckDB analytical warehouse."""
        return self.processed_dir / "warehouse.duckdb"

    @property
    def llm_available(self) -> bool:
        """True only when an API key is present *and* the feature is enabled."""
        return bool(self.anthropic_api_key) and self.llm_briefing_enabled

    def ensure_directories(self) -> None:
        """Create the data directories if they do not yet exist."""
        for path in (self.data_dir, self.raw_dir, self.processed_dir, self.sample_dir):
            path.mkdir(parents=True, exist_ok=True)


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


@functools.lru_cache(maxsize=1)
def get_source_config() -> dict[str, Any]:
    """Load and cache the YAML source configuration."""
    path = get_settings().sources_config_path
    if not path.exists():
        raise FileNotFoundError(
            f"Source configuration not found at {path}. "
            "It is required for ingestion; see config/sources.yaml."
        )
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_region_lookup() -> dict[str, str]:
    """Region code -> region name, from the source configuration."""
    return dict(get_source_config().get("regions", {}))
