"""Canonical analytical schema and source-to-canonical column mapping.

The published NHS England workbooks use long, human-readable, occasionally
restated column captions. This module is the single place where those captions
are mapped onto stable canonical field names. When NHS England renames a
column, only this file changes.

Every canonical measure here exists in the published source. Nothing is
invented: measures that a given vintage does not publish are left null and
excluded from downstream metrics rather than imputed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Dimension key columns, common to every provider-level RTT workbook ------
DIMENSION_COLUMNS: dict[str, str] = {
    "region code": "region_code",
    "provider code": "provider_code",
    "provider name": "provider_name",
    "treatment function code": "specialty_code",
    "treatment function": "specialty_name",
}


@dataclass(frozen=True)
class DatasetSpec:
    """Describes how one published workbook maps onto canonical measures."""

    key: str
    label: str
    # Lower-cased published caption -> canonical measure name.
    measures: dict[str, str]
    # Canonical measures that must be present for the file to be usable.
    required_measures: tuple[str, ...]
    # Canonical measures derived from the weekly bands rather than a total.
    weekly_band_measures: dict[str, str] = field(default_factory=dict)


INCOMPLETE_SPEC = DatasetSpec(
    key="incomplete",
    label="Incomplete pathways (waiting list)",
    measures={
        "total number of incomplete pathways": "total_incomplete_pathways",
        "total within 18 weeks": "within_18_weeks",
        "% within 18 weeks": "pct_within_18_weeks_published",
        "average (median) waiting time (in weeks)": "median_wait_weeks",
        "92nd percentile waiting time (in weeks)": "percentile_92_wait_weeks",
        "total 52 plus weeks": "over_52_weeks",
        "total 65 plus weeks": "over_65_weeks",
        "total 78 plus weeks": "over_78_weeks",
        "% 52 plus weeks": "pct_over_52_weeks_published",
        "104 plus": "over_104_weeks",
    },
    required_measures=("total_incomplete_pathways", "within_18_weeks"),
)

ADMITTED_SPEC = DatasetSpec(
    key="admitted",
    label="Completed admitted pathways",
    measures={
        "total number of completed pathways (all)": "admitted_activity",
        "total number of completed pathways (with a known clock start)": (
            "admitted_activity_known_clock_start"
        ),
        "average (median) waiting time (in weeks)": "admitted_median_wait_weeks",
    },
    required_measures=("admitted_activity",),
)

NON_ADMITTED_SPEC = DatasetSpec(
    key="non_admitted",
    label="Completed non-admitted pathways",
    measures={
        "total number of completed pathways (all)": "non_admitted_activity",
        "total number of completed pathways (with a known clock start)": (
            "non_admitted_activity_known_clock_start"
        ),
        "average (median) waiting time (in weeks)": "non_admitted_median_wait_weeks",
    },
    required_measures=("non_admitted_activity",),
)

DATASET_SPECS: dict[str, DatasetSpec] = {
    "incomplete": INCOMPLETE_SPEC,
    "admitted": ADMITTED_SPEC,
    "non_admitted": NON_ADMITTED_SPEC,
}


# --- Canonical fact grain ---------------------------------------------------
FACT_GRAIN: tuple[str, ...] = ("provider_code", "specialty_code", "reporting_month")

# Measures carried on fact_rtt. Nullable where the source does not publish them.
FACT_MEASURES: tuple[str, ...] = (
    "total_incomplete_pathways",
    "within_18_weeks",
    "over_18_weeks",
    "over_52_weeks",
    "over_65_weeks",
    "over_78_weeks",
    "over_104_weeks",
    "median_wait_weeks",
    "percentile_92_wait_weeks",
    "admitted_activity",
    "non_admitted_activity",
    "completed_pathways",
)

# Counts that must never be negative in a valid published file.
NON_NEGATIVE_MEASURES: tuple[str, ...] = (
    "total_incomplete_pathways",
    "within_18_weeks",
    "over_18_weeks",
    "over_52_weeks",
    "over_65_weeks",
    "over_78_weeks",
    "over_104_weeks",
    "admitted_activity",
    "non_admitted_activity",
    "completed_pathways",
)

# Fields expressed as percentages, which must sit within [0, 100].
PERCENTAGE_FIELDS: tuple[str, ...] = (
    "pct_within_18_weeks",
    "pct_over_18_weeks",
    "pct_over_52_weeks",
    "pct_over_65_weeks",
    "pct_over_78_weeks",
)

DATA_SOURCE_OFFICIAL = "OFFICIAL_NHS_PUBLIC"
DATA_SOURCE_DEMO = "DEMO_SYNTHETIC"


def normalise_caption(caption: object) -> str:
    """Normalise a published column caption for lookup.

    Handles the whitespace, casing and non-breaking-space variations that
    appear between publication vintages.
    """
    if caption is None:
        return ""
    text = str(caption)
    text = text.replace("\u00a0", " ").replace("\n", " ")
    return " ".join(text.split()).strip().lower()


def build_column_map(captions: list[object], spec: DatasetSpec) -> dict[int, str]:
    """Map worksheet column indices onto canonical names for one dataset.

    Returns ``{column_index: canonical_name}``. Captions that are not part of
    the canonical model (the ~105 individual weekly bands) are ignored, except
    the ``104 plus`` band which the incomplete spec promotes to a measure.
    """
    lookup = {**DIMENSION_COLUMNS, **spec.measures}
    mapping: dict[int, str] = {}
    seen: set[str] = set()
    for index, caption in enumerate(captions):
        key = normalise_caption(caption)
        canonical = lookup.get(key)
        if canonical is None or canonical in seen:
            continue
        mapping[index] = canonical
        seen.add(canonical)
    return mapping
