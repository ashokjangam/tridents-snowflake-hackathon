"""Classify a question before any warehouse call."""

from __future__ import annotations

import re

from app.models import Intent

_CHANGE_VERB = re.compile(
    r"\b(change|increase|decrease|adjust|raise|lower|stop|discontinue|prescribe|taper|modify)\b",
    re.IGNORECASE,
)
_CHANGE_OBJECT = re.compile(
    r"\b(dose|doses|prescription|medication|medications|meds|fexofenadine|antihistamine)\b",
    re.IGNORECASE,
)
_NEW_PRESCRIPTION = re.compile(r"\bnew prescription\b", re.IGNORECASE)
_START_MEDICATION = re.compile(
    r"\bstart\b.{0,40}\b(medication|prescription|fexofenadine|antihistamine)\b",
    re.IGNORECASE,
)
_DISCHARGE = re.compile(
    r"\b(discharge summary|discharge note|progress note)\b",
    re.IGNORECASE,
)
_EXTERNAL = re.compile(
    r"\b(open\s*fda|fda label|regulatory label|drug label|external claims?)\b",
    re.IGNORECASE,
)
_TREATMENT = re.compile(
    r"\bwhat should (we|i|the patient)\b"
    r"|\bhow should (we|i) treat\b"
    r"|\b(treatment advice|care recommendation|next best action)\b"
    r"|\brecommend(?:ation)?\b"
    r"|\bshould (we|i) (treat|start|stop|prescribe|give)\b",
    re.IGNORECASE,
)
_RISK = re.compile(
    r"\bpoint count\b|\bfrozen 2023\b|\b2023 cohort\b|\brisk panel\b|\brisk score\b",
    re.IGNORECASE,
)
_ALLERGY = re.compile(r"\ballerg", re.IGNORECASE)
_MEDICATION = re.compile(r"\b(antihistamine|fexofenadine)\b", re.IGNORECASE)
_MEDICATION_LIST = re.compile(
    r"\b(medication list|medications|medicines|dispenses?)\b", re.IGNORECASE
)
_CONDITION = re.compile(
    r"\b(active conditions?|condition history|conditions?|problems?|diagnoses|diagnosis)\b",
    re.IGNORECASE,
)
_CARE_PLAN = re.compile(r"\bcare\s*plans?|plan of care\b", re.IGNORECASE)
_LAB = re.compile(
    r"\b(labs?|laboratory|observations?|a1c|hba1c|hemoglobin a1c)\b", re.IGNORECASE
)
_PROCEDURE = re.compile(r"\bprocedures?|surgeries|surgical\b", re.IGNORECASE)
_IMMUNIZATION = re.compile(r"\bimmuni[sz]ations?|vaccines?|vaccinations?\b", re.IGNORECASE)
_CLAIM = re.compile(r"\bclaims?|billing|appointment id|claim encounter\b", re.IGNORECASE)
_COVERAGE = re.compile(r"\bcoverage|payer|insurance|member id\b", re.IGNORECASE)
_MEMBER_SUMMARY = re.compile(
    r"\b(member summary|patient summary|recent encounters?|encounter history|chart summary)\b",
    re.IGNORECASE,
)

_REFUSAL_INTENTS = (
    Intent.REFUSE_MEDICATION_CHANGE,
    Intent.REFUSE_DISCHARGE,
    Intent.REFUSE_EXTERNAL,
    Intent.REFUSE_TREATMENT,
)


def refusal_intents(question: str) -> tuple[Intent, ...]:
    """Return every hard refusal the question triggers, in screen order."""
    text = " ".join(question.split())
    if not text:
        return ()
    found: list[Intent] = []
    if _medication_change(text):
        found.append(Intent.REFUSE_MEDICATION_CHANGE)
    if _DISCHARGE.search(text):
        found.append(Intent.REFUSE_DISCHARGE)
    if _EXTERNAL.search(text):
        found.append(Intent.REFUSE_EXTERNAL)
    if _TREATMENT.search(text):
        found.append(Intent.REFUSE_TREATMENT)
    return tuple(found)


def classify_intent(question: str) -> Intent:
    """Classify one question. Refusals win over chart lookup."""
    text = " ".join(question.split())
    if not text:
        return Intent.NO_CITATION
    refusals = refusal_intents(text)
    if refusals:
        return refusals[0]
    if _RISK.search(text):
        return Intent.RISK_COHORT
    if _ALLERGY.search(text):
        return Intent.ALLERGY_CITATION
    if _MEDICATION.search(text):
        return Intent.MEDICATION_CITATION
    if _MEDICATION_LIST.search(text):
        return Intent.MEDICATION_LIST
    if _CARE_PLAN.search(text):
        return Intent.CARE_PLAN_LIST
    if _CONDITION.search(text):
        return Intent.CONDITION_LIST
    if _LAB.search(text):
        return Intent.LAB_RESULTS
    if _PROCEDURE.search(text):
        return Intent.PROCEDURE_LIST
    if _IMMUNIZATION.search(text):
        return Intent.IMMUNIZATION_LIST
    if _CLAIM.search(text):
        return Intent.CLAIM_ENCOUNTER
    if _COVERAGE.search(text):
        return Intent.COVERAGE_LIST
    if _MEMBER_SUMMARY.search(text):
        return Intent.MEMBER_SUMMARY
    return Intent.NO_CITATION


def _medication_change(text: str) -> bool:
    if _NEW_PRESCRIPTION.search(text) or _START_MEDICATION.search(text):
        return True
    return _CHANGE_VERB.search(text) is not None and _CHANGE_OBJECT.search(text) is not None
