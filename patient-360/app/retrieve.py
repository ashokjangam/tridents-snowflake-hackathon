"""Which warehouse steps a question needs. The page executes the steps."""

from __future__ import annotations

from app.compat import assert_never
from app.intents import classify_intent, refusal_intents
from app.models import Intent
from app.text_parse import synthea_name


def retrieval_steps(question: str, selected_patient_id: str | None) -> tuple[str, ...]:
    """Ordered query names. A refusal has no query."""
    if refusal_intents(question):
        return ()
    intent = classify_intent(question)
    if intent is Intent.NO_CITATION:
        return ()
    if intent is Intent.RISK_COHORT:
        return ("risk",)
    if intent is Intent.MEMBER_SUMMARY:
        return _patient_steps(question, selected_patient_id, "member_summary", "recent_encounters")
    if intent is Intent.CONDITION_LIST:
        return _patient_steps(question, selected_patient_id, "condition_evidence", "problem_section")
    if intent is Intent.MEDICATION_LIST:
        return _patient_steps(question, selected_patient_id, "medication_evidence", "medication_full_section")
    if intent is Intent.CARE_PLAN_LIST:
        return _patient_steps(question, selected_patient_id, "care_plan_evidence", "care_plan_section")
    if intent is Intent.LAB_RESULTS:
        return _patient_steps(question, selected_patient_id, "lab_evidence")
    if intent is Intent.PROCEDURE_LIST:
        return _patient_steps(question, selected_patient_id, "procedure_evidence", "procedure_section")
    if intent is Intent.IMMUNIZATION_LIST:
        return _patient_steps(
            question, selected_patient_id, "immunization_evidence", "immunization_section"
        )
    if intent is Intent.CLAIM_ENCOUNTER:
        return _patient_steps(question, selected_patient_id, "claim_evidence")
    if intent is Intent.COVERAGE_LIST:
        return _patient_steps(question, selected_patient_id, "coverage_evidence")
    if intent is Intent.MEDICATION_CITATION:
        return _patient_steps(question, selected_patient_id, "antihistamine", "medication_section")
    if intent is Intent.ALLERGY_CITATION:
        return _patient_steps(
            question, selected_patient_id, "member_summary", "allergy", "allergy_section"
        )
    if intent in {
        Intent.REFUSE_MEDICATION_CHANGE,
        Intent.REFUSE_DISCHARGE,
        Intent.REFUSE_EXTERNAL,
        Intent.REFUSE_TREATMENT,
    }:
        return ()
    assert_never(intent)


def _patient_steps(
    question: str, selected_patient_id: str | None, *steps: str
) -> tuple[str, ...]:
    if synthea_name(question) is None and not selected_patient_id:
        return ()
    prefix = ("patient_name",) if synthea_name(question) is not None else ()
    return (*prefix, *steps)
