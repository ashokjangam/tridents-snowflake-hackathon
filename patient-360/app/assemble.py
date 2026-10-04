"""Turn a question plus already-retrieved rows into one answer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.answers import (
    answer_allergy,
    answer_claims,
    answer_clinical_list,
    answer_coverage,
    answer_labs,
    answer_medication,
    answer_member_summary,
    answer_risk,
)
from app.compat import assert_never
from app.guardrails import (
    REFUSE_NO_CITATION,
    REFUSE_NO_WAREHOUSE,
    REFUSE_QUERY_FAILED,
    combined_refusal,
    refuse,
)
from app.intents import classify_intent, refusal_intents
from app.models import Answer, Intent
from app.rows import normalize_row
from app.text_parse import synthea_name


def resolve_patient_id(
    question: str,
    selected_patient_id: str | None,
    name_rows: Sequence[Mapping[str, object]],
) -> str | None:
    """Use a named person when the question has one, otherwise the selector."""
    if synthea_name(question) is None:
        return selected_patient_id
    if len(name_rows) != 1:
        return None
    return normalize_row(name_rows[0]).get("patient_id")


def assemble_answer(
    question: str,
    *,
    selected_patient_id: str | None = None,
    name_rows: Sequence[Mapping[str, object]] = (),
    medication_rows: Sequence[Mapping[str, object]] = (),
    section_rows: Sequence[Mapping[str, object]] = (),
    allergy_rows: Sequence[Mapping[str, object]] = (),
    risk_rows: Sequence[Mapping[str, object]] = (),
    evidence_rows: Sequence[Mapping[str, object]] = (),
    related_rows: Sequence[Mapping[str, object]] = (),
    warehouse_connected: bool = True,
    query_failed: bool = False,
) -> Answer:
    """Answer from rows, or refuse. Refusals ignore any rows that were passed in."""
    refusals = refusal_intents(question)
    if refusals:
        return combined_refusal(refusals)
    intent = classify_intent(question)
    if query_failed:
        return refuse(intent, REFUSE_QUERY_FAILED)
    if intent is Intent.NO_CITATION:
        return refuse(intent, REFUSE_NO_CITATION)
    if not warehouse_connected:
        return refuse(intent, REFUSE_NO_WAREHOUSE)
    if intent is Intent.RISK_COHORT:
        return answer_risk(risk_rows)
    patient_id = resolve_patient_id(question, selected_patient_id, name_rows)
    if synthea_name(question) is not None and patient_id is None:
        return refuse(
            intent,
            "Refused. The name in the question did not match exactly one patient, so nothing is cited.",
        )
    if patient_id is None:
        return refuse(
            intent,
            "Refused. No patient is selected, so no row is cited.",
        )
    if intent is Intent.MEDICATION_CITATION:
        medications = _for_patient(medication_rows, patient_id)
        sections = _for_patient(section_rows, patient_id)
        patients = name_rows if synthea_name(question) is not None else ()
        return answer_medication(medications, sections, patients)
    if intent is Intent.ALLERGY_CITATION:
        allergies = _for_patient(allergy_rows, patient_id)
        sections = _for_patient(section_rows, patient_id)
        patients = _for_patient(evidence_rows, patient_id)
        return answer_allergy(allergies, sections, patients)
    evidence = _for_patient(evidence_rows, patient_id)
    sections = _for_patient(section_rows, patient_id)
    if intent is Intent.MEMBER_SUMMARY:
        return answer_member_summary(evidence, _for_patient(related_rows, patient_id))
    if intent is Intent.CONDITION_LIST:
        return answer_clinical_list(intent, "CONDITION", "Condition evidence", evidence, sections)
    if intent is Intent.MEDICATION_LIST:
        return answer_clinical_list(intent, "MEDICATION", "Medication evidence", evidence, sections)
    if intent is Intent.CARE_PLAN_LIST:
        return answer_clinical_list(intent, "CAREPLAN", "Care-plan evidence", evidence, sections)
    if intent is Intent.LAB_RESULTS:
        return answer_labs(evidence)
    if intent is Intent.PROCEDURE_LIST:
        return answer_clinical_list(intent, "PROCEDURE", "Procedure evidence", evidence, sections)
    if intent is Intent.IMMUNIZATION_LIST:
        return answer_clinical_list(
            intent, "IMMUNIZATION", "Immunization evidence", evidence, sections
        )
    if intent is Intent.CLAIM_ENCOUNTER:
        return answer_claims(evidence)
    if intent is Intent.COVERAGE_LIST:
        return answer_coverage(evidence)
    assert_never(intent)


def _for_patient(
    rows: Sequence[Mapping[str, object]],
    patient_id: str,
) -> tuple[Mapping[str, object], ...]:
    return tuple(row for row in rows if normalize_row(row).get("patient_id") == patient_id)
