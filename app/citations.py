"""Citation tuples and the allergy-code guard."""

from __future__ import annotations

import re

from app.compat import assert_never
from app.models import (
    Citation,
    ClaimCitation,
    CohortCitation,
    CoverageCitation,
    DocumentCitation,
    EncounterCitation,
    ObservationCitation,
    PatientCitation,
    TableCitation,
)

_CODE_RUN = re.compile(r"\d{6,18}")
_RISK_TABLE = "RISK_SCORE"


def digit_codes(value: str | None) -> tuple[str, ...]:
    """Return identifier-length codes, skipping compact CDA timestamps."""
    if not value:
        return ()
    found: list[str] = []
    for code in _CODE_RUN.findall(value):
        if len(code) >= 12 or code in found:
            continue
        found.append(code)
    return tuple(found)


def codes_match(left: str | None, right: str | None) -> bool:
    """True when two cells share one code."""
    left_codes = digit_codes(left)
    right_codes = digit_codes(right)
    if not left_codes or not right_codes:
        return False
    return any(code in right_codes for code in left_codes)


def conflicting_codes(csv_code: str, candidates: tuple[str | None, ...]) -> tuple[str, ...]:
    """Codes present beside the CSV code. The CSV code itself is omitted."""
    keep = set(digit_codes(csv_code))
    found: list[str] = []
    for candidate in candidates:
        for code in digit_codes(candidate):
            if code in keep or code in found:
                continue
            found.append(code)
    return tuple(found)


def format_citation(citation: Citation) -> str:
    """Render one citation as the tuple the page and the narrator must keep."""
    if isinstance(citation, DocumentCitation):
        fields = (
            ("document_id", citation.document_id),
            ("section_loinc", citation.section_loinc),
            ("element_id", citation.element_id),
        )
    elif isinstance(citation, TableCitation):
        fields = (
            ("table", citation.table),
            ("patient_id", citation.patient_id),
            ("encounter_id", citation.encounter_id),
            ("code", citation.code),
            ("start", citation.start),
        )
    elif isinstance(citation, CohortCitation):
        fields = (
            ("table", citation.table),
            ("index_date", citation.index_date),
            ("horizon_end", citation.horizon_end),
            ("score", citation.score),
        )
    elif isinstance(citation, PatientCitation):
        fields = (("table", citation.table), ("patient_id", citation.patient_id))
    elif isinstance(citation, EncounterCitation):
        fields = (
            ("table", citation.table),
            ("patient_id", citation.patient_id),
            ("encounter_id", citation.encounter_id),
            ("start", citation.start),
        )
    elif isinstance(citation, ObservationCitation):
        fields = (
            ("table", citation.table),
            ("patient_id", citation.patient_id),
            ("row_id", citation.row_id),
            ("code", citation.code),
            ("observed_at", citation.observed_at),
        )
    elif isinstance(citation, ClaimCitation):
        fields = (
            ("table", citation.table),
            ("patient_id", citation.patient_id),
            ("claim_id", citation.claim_id),
            ("encounter_id", citation.encounter_id),
            ("service_date", citation.service_date),
        )
    elif isinstance(citation, CoverageCitation):
        fields = (
            ("table", citation.table),
            ("patient_id", citation.patient_id),
            ("payer_id", citation.payer_id),
            ("start", citation.start),
            ("end", citation.end),
        )
    else:
        assert_never(citation)
    return _render(fields)


def validate_citation(citation: Citation) -> tuple[str, ...]:
    """Return problems. An element id without its document id is a problem."""
    if isinstance(citation, DocumentCitation):
        problems: list[str] = []
        if not citation.document_id.strip():
            problems.append("document_id is required because element ids restart across files")
        if not citation.section_loinc.strip():
            problems.append("section_loinc is required")
        if not citation.element_id.strip():
            problems.append("element_id is required")
        return tuple(problems)
    if isinstance(citation, TableCitation):
        if citation.table == _RISK_TABLE:
            return ("RISK_SCORE uses a cohort citation",)
        return _missing(
            "table",
            (
                ("table", citation.table),
                ("patient_id", citation.patient_id),
                ("encounter_id", citation.encounter_id),
                ("code", citation.code),
                ("start", citation.start),
            ),
        )
    if isinstance(citation, CohortCitation):
        missing = [
            name
            for name, value in (
                ("table", citation.table),
                ("index_date", citation.index_date),
                ("horizon_end", citation.horizon_end),
                ("score", citation.score),
            )
            if not value.strip()
        ]
        if citation.table != _RISK_TABLE:
            missing.append("cohort citation table must be RISK_SCORE")
        if missing:
            return (f"cohort citation missing {', '.join(missing)}",)
        return ()
    if isinstance(citation, PatientCitation):
        return _missing("patient", (("table", citation.table), ("patient_id", citation.patient_id)))
    if isinstance(citation, EncounterCitation):
        return _missing(
            "encounter",
            (
                ("table", citation.table),
                ("patient_id", citation.patient_id),
                ("encounter_id", citation.encounter_id),
                ("start", citation.start),
            ),
        )
    if isinstance(citation, ObservationCitation):
        return _missing(
            "observation",
            (
                ("table", citation.table),
                ("patient_id", citation.patient_id),
                ("row_id", citation.row_id),
                ("code", citation.code),
                ("observed_at", citation.observed_at),
            ),
        )
    if isinstance(citation, ClaimCitation):
        return _missing(
            "claim",
            (
                ("table", citation.table),
                ("patient_id", citation.patient_id),
                ("claim_id", citation.claim_id),
                ("encounter_id", citation.encounter_id),
                ("service_date", citation.service_date),
            ),
        )
    if isinstance(citation, CoverageCitation):
        return _missing(
            "coverage",
            (
                ("table", citation.table),
                ("patient_id", citation.patient_id),
                ("payer_id", citation.payer_id),
                ("start", citation.start),
                ("end", citation.end),
            ),
        )
    assert_never(citation)


def _render(fields: tuple[tuple[str, str], ...]) -> str:
    return "(" + ", ".join(f"{name}={value}" for name, value in fields) + ")"


def _missing(kind: str, fields: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    names = [name for name, value in fields if not value.strip()]
    if not names:
        return ()
    return (f"{kind} citation missing {', '.join(names)}",)


def rejected_code_is_guarded(text: str, quoted_code: str, rejected_code: str) -> bool:
    """A rejected code may appear only with a nearby negation and the CSV code."""
    if rejected_code not in text:
        return True
    if quoted_code not in text:
        return False
    for match in re.finditer(re.escape(rejected_code), text):
        window = text[max(0, match.start() - 80) : match.start()].lower()
        if "not" not in window:
            return False
    return True
