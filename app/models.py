"""Shared answer and citation types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Union


class Intent(Enum):
    """Question classes the page can answer or refuse."""

    MEMBER_SUMMARY = "member_summary"
    CONDITION_LIST = "condition_list"
    MEDICATION_CITATION = "medication_citation"
    MEDICATION_LIST = "medication_list"
    ALLERGY_CITATION = "allergy_citation"
    CARE_PLAN_LIST = "care_plan_list"
    LAB_RESULTS = "lab_results"
    PROCEDURE_LIST = "procedure_list"
    IMMUNIZATION_LIST = "immunization_list"
    CLAIM_ENCOUNTER = "claim_encounter"
    COVERAGE_LIST = "coverage_list"
    RISK_COHORT = "risk_cohort"
    REFUSE_MEDICATION_CHANGE = "refuse_medication_change"
    REFUSE_DISCHARGE = "refuse_discharge"
    REFUSE_EXTERNAL = "refuse_external"
    REFUSE_TREATMENT = "refuse_treatment"
    NO_CITATION = "no_citation"


class AnswerStatus(Enum):
    """Whether retrieved rows supported a citation tuple."""

    CITED = "cited"
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class DocumentCitation:
    """C-CDA citation. Element ids restart across files, so document_id stays."""

    document_id: str
    section_loinc: str
    element_id: str

    def as_tuple(self) -> tuple[str, str, str]:
        return (self.document_id, self.section_loinc, self.element_id)


@dataclass(frozen=True, slots=True)
class TableCitation:
    """Structured-row citation. Clinical tables in this sample have no row id."""

    table: str
    patient_id: str
    encounter_id: str
    code: str
    start: str

    def as_tuple(self) -> tuple[str, str, str, str, str]:
        return (self.table, self.patient_id, self.encounter_id, self.code, self.start)


@dataclass(frozen=True, slots=True)
class CohortCitation:
    """Risk-view citation. The cohort question has no patient row to invent."""

    table: str
    index_date: str
    horizon_end: str
    score: str

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.table, self.index_date, self.horizon_end, self.score)


@dataclass(frozen=True, slots=True)
class PatientCitation:
    """A patient row without exposing a clinical or financial identifier."""

    table: str
    patient_id: str

    def as_tuple(self) -> tuple[str, str]:
        return (self.table, self.patient_id)


@dataclass(frozen=True, slots=True)
class EncounterCitation:
    """An encounter row tied to the selected patient."""

    table: str
    patient_id: str
    encounter_id: str
    start: str

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.table, self.patient_id, self.encounter_id, self.start)


@dataclass(frozen=True, slots=True)
class ObservationCitation:
    """An observation can legitimately have no encounter in Synthea."""

    table: str
    patient_id: str
    row_id: str
    code: str
    observed_at: str

    def as_tuple(self) -> tuple[str, str, str, str, str]:
        return (self.table, self.patient_id, self.row_id, self.code, self.observed_at)


@dataclass(frozen=True, slots=True)
class ClaimCitation:
    """Claim key plus the encounter carried by APPOINTMENT_ID."""

    table: str
    patient_id: str
    claim_id: str
    encounter_id: str
    service_date: str

    def as_tuple(self) -> tuple[str, str, str, str, str]:
        return (self.table, self.patient_id, self.claim_id, self.encounter_id, self.service_date)


@dataclass(frozen=True, slots=True)
class CoverageCitation:
    """Coverage span citation; MEMBER_ID is deliberately not required."""

    table: str
    patient_id: str
    payer_id: str
    start: str
    end: str

    def as_tuple(self) -> tuple[str, str, str, str, str]:
        return (self.table, self.patient_id, self.payer_id, self.start, self.end)


Citation = Union[
    DocumentCitation,
    TableCitation,
    CohortCitation,
    PatientCitation,
    EncounterCitation,
    ObservationCitation,
    ClaimCitation,
    CoverageCitation,
]


@dataclass(frozen=True, slots=True)
class Answer:
    """Deterministic answer. Narration is allowed only when a citation exists."""

    status: AnswerStatus
    intent: Intent
    text: str
    citations: tuple[Citation, ...]
    narration_allowed: bool
    quoted_codes: tuple[str, ...] = ()
    rejected_codes: tuple[str, ...] = ()
