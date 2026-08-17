"""Cleaning and standardisation of parsed workbook frames."""

from __future__ import annotations

import re

import pandas as pd

from app.config import get_source_config
from app.utils.logging import get_logger

logger = get_logger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")

# Suffixes stripped when producing a compact display name for charts and tables.
_NAME_NOISE = (
    " NHS FOUNDATION TRUST",
    " NHS TRUST",
    " NHS FOUNDATION TRUST (THE)",
)


def _tidy_text(series: pd.Series) -> pd.Series:
    """Trim, collapse internal whitespace and normalise empty strings to null."""
    cleaned = (
        series.astype("string")
        .str.replace("\u00a0", " ", regex=False)
        .str.strip()
        .str.replace(_WHITESPACE_RE, " ", regex=True)
    )
    return cleaned.replace({"": pd.NA})


# Words kept lower case inside a title-cased name (never in first position).
_MINOR_WORDS = {
    "and", "of", "the", "for", "in", "on", "at", "to", "upon", "with",
}

# Published names that must keep their upper-case form.
_ACRONYMS = {"NHS", "UHB", "HQ", "GP", "ICB", "ENT"}


def title_case_provider(name: str | None) -> str | None:
    """Convert SHOUTED provider names into readable title case.

    NHS England publishes provider names in upper case. Rendering 155 upper-case
    trust names in a dashboard is genuinely hard to scan.

    ``str.title()`` alone is not sufficient: it capitalises the letter after an
    apostrophe, producing "Alder Hey Children'S", and it capitalises
    conjunctions. Both are handled here.
    """
    if name is None or pd.isna(name):
        return None

    # Trailing punctuation appears in a few published names, e.g.
    # "THE QUEEN ELIZABETH HOSPITAL, KING'S LYNN,".
    text = str(name).strip().rstrip(",;")

    words = text.split()
    result: list[str] = []
    for index, word in enumerate(words):
        stripped = word.strip(",.()")
        if stripped.upper() in _ACRONYMS:
            result.append(word.upper())
            continue
        lowered = word.lower()
        if index > 0 and stripped.lower() in _MINOR_WORDS:
            result.append(lowered)
            continue
        # Capitalise the first letter of each hyphenated part, but never the
        # letter following an apostrophe.
        result.append(
            re.sub(
                r"(^|[\s\-/(])([a-z])",
                lambda m: m.group(1) + m.group(2).upper(),
                lowered,
            )
        )
    return " ".join(result)


def short_provider_name(name: str | None) -> str | None:
    """Compact provider label for axis ticks and dense tables."""
    if name is None or pd.isna(name):
        return None
    upper = str(name).upper()
    for suffix in _NAME_NOISE:
        if upper.endswith(suffix):
            upper = upper[: -len(suffix)]
            break
    return title_case_provider(upper)


def short_specialty_name(name: str | None) -> str | None:
    """Drop the redundant trailing 'Service' from treatment function names."""
    if name is None or pd.isna(name):
        return None
    text = str(name).strip()
    if text.endswith(" Service"):
        text = text[: -len(" Service")]
    return text


def clean_frame(frame: pd.DataFrame, dataset: str) -> pd.DataFrame:
    """Standardise one parsed workbook frame.

    - trims and normalises text
    - upper-cases organisation and treatment-function codes
    - drops aggregate rows configured as exclusions
    - converts the published fractional percentages to 0-100
    - de-duplicates the grain, keeping the last occurrence
    """
    cfg = get_source_config()["sources"]["rtt"]
    result = frame.copy()

    for column in ("region_code", "provider_code", "provider_name",
                   "specialty_code", "specialty_name"):
        if column in result.columns:
            result[column] = _tidy_text(result[column])

    for column in ("region_code", "provider_code", "specialty_code"):
        if column in result.columns:
            result[column] = result[column].str.upper()

    before = len(result)
    excluded_specialties = {
        str(c).upper() for c in cfg.get("excluded_specialty_codes") or []
    }
    excluded_providers = {
        str(c).upper() for c in cfg.get("excluded_provider_codes") or []
    }
    if excluded_specialties and "specialty_code" in result.columns:
        result = result[~result["specialty_code"].isin(excluded_specialties)]
    if excluded_providers and "provider_code" in result.columns:
        result = result[~result["provider_code"].isin(excluded_providers)]
    if before != len(result):
        logger.info(
            "Removed %d aggregate rows from %s", before - len(result), dataset
        )

    result = result.dropna(subset=["provider_code", "specialty_code"])

    # NHS England publishes '% within 18 weeks' as a fraction (0.5115), while
    # this product works in percentage points throughout. Detect and rescale
    # rather than assuming, so a future change of units does not double-scale.
    for published, canonical in (
        ("pct_within_18_weeks_published", "pct_within_18_weeks_source"),
        ("pct_over_52_weeks_published", "pct_over_52_weeks_source"),
    ):
        if published in result.columns:
            values = pd.to_numeric(result[published], errors="coerce")
            finite = values.dropna()
            if not finite.empty and float(finite.max()) <= 1.5:
                values = values * 100.0
            result[canonical] = values.clip(lower=0.0, upper=100.0)
            result = result.drop(columns=[published])

    grain = [c for c in ("provider_code", "specialty_code", "reporting_month")
             if c in result.columns]
    if grain:
        result = result.drop_duplicates(subset=grain, keep="last")

    return result.reset_index(drop=True)
