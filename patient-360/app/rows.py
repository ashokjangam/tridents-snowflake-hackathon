"""Normalize warehouse rows to lowercase citation fields."""

from __future__ import annotations

import math
from collections.abc import Mapping

_ALIASES: dict[str, tuple[str, ...]] = {
    "patient_id": ("patient_id", "patient"),
    "encounter_id": ("encounter_id", "encounter"),
    "start": ("start", "start_ts", "start_date", "observed_at", "service_date"),
    "code": ("code",),
    "description": ("description",),
    "document_id": ("document_id",),
    "section_loinc": ("section_loinc",),
    "section_title": ("section_title",),
    "element_id": ("element_id",),
    "text": ("text",),
    "rejected_codes": ("rejected_codes",),
    "first_name": ("first_name", "first"),
    "last_name": ("last_name", "last"),
    "score": ("score", "point_score"),
    "patient_count": ("patient_count", "patients"),
    "bucket_event_count": ("bucket_event_count",),
    "event_rate": ("event_rate",),
    "cohort_n": ("cohort_n", "cohort_size"),
    "event_n": ("event_n", "events"),
    "base_rate": ("base_rate",),
    "ge2_patient_count": ("ge2_patient_count",),
    "ge2_event_rate": ("ge2_event_rate",),
    "index_date": ("index_date",),
    "horizon_end": ("horizon_end",),
    "excluded_dead": ("excluded_dead",),
    "excluded_born": ("excluded_born",),
}


def stringify(value: object) -> str | None:
    """Return a stripped string, or None for empty and null warehouse values."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"none", "nan", "null"}:
        return None
    return text


def normalize_row(row: Mapping[str, object]) -> dict[str, str | None]:
    """Lowercase keys and fill citation aliases without dropping extra columns."""
    lowered = {str(key).lower(): stringify(value) for key, value in row.items()}
    normalized = dict(lowered)
    for canonical, aliases in _ALIASES.items():
        if normalized.get(canonical):
            continue
        for alias in aliases:
            candidate = lowered.get(alias)
            if candidate:
                normalized[canonical] = candidate
                break
    return normalized
