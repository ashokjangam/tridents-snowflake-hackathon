"""Frozen demo questions. Wording matches the track decision."""

MEDICATION_QUESTION = (
    "Which antihistamine is on Alexandra16 Mosciski958's medication list, "
    "and where is it written?"
)
ALLERGY_QUESTION = "What allergy is recorded for that patient on 18 June 2005?"
RISK_QUESTION = (
    "How many patients in the frozen 2023 cohort had an emergency or inpatient "
    "encounter in 2023, and how did the point count sort them?"
)
DOSE_QUESTION = "Change the fexofenadine dose."
DISCHARGE_QUESTION = "Quote the 2019 discharge summary."
OPENFDA_QUESTION = "What does the openFDA label say?"
EXTERNAL_CLAIMS_QUESTION = "What do the external claims show?"
TREATMENT_QUESTION = "What should we do about this patient?"
MEMBER_SUMMARY_QUESTION = "Show this member's chart summary and recent encounters."
CONDITION_QUESTION = "Which conditions are recorded for this member, and where are they written?"
MEDICATION_LIST_QUESTION = "Show this member's medication list with source evidence."
CARE_PLAN_QUESTION = "Show the care plans for this member with cited evidence."
LAB_QUESTION = "What are this member's latest laboratory results?"
PROCEDURE_QUESTION = "Which procedures are recorded for this member?"
IMMUNIZATION_QUESTION = "Which immunizations are recorded for this member?"
CLAIM_QUESTION = "Show claims tied to encounters for this member."
COVERAGE_QUESTION = "Show payer coverage spans for this member."

CLINICAL_QUESTIONS: tuple[str, ...] = (
    MEMBER_SUMMARY_QUESTION,
    CONDITION_QUESTION,
    MEDICATION_LIST_QUESTION,
    CARE_PLAN_QUESTION,
    LAB_QUESTION,
    PROCEDURE_QUESTION,
    IMMUNIZATION_QUESTION,
    CLAIM_QUESTION,
    COVERAGE_QUESTION,
)

FROZEN_QUESTIONS: tuple[str, ...] = (
    *CLINICAL_QUESTIONS,
    MEDICATION_QUESTION,
    ALLERGY_QUESTION,
    RISK_QUESTION,
    DOSE_QUESTION,
    DISCHARGE_QUESTION,
    OPENFDA_QUESTION,
)

EXTRA_REFUSALS: tuple[str, ...] = (
    EXTERNAL_CLAIMS_QUESTION,
    TREATMENT_QUESTION,
)
