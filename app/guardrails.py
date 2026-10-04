"""Refusal text and banned clinical claims."""

from __future__ import annotations

from app.models import Answer, AnswerStatus, Intent

REFUSE_MEDICATION_CHANGE = (
    "Refused. This demo does not change a dose, start a prescription, stop a medication, "
    "or write an order. No dose-change row is an order."
)
REFUSE_DISCHARGE = (
    "Refused. There is no discharge summary or progress note to cite, including for 2019. "
    "Each C-CDA in this sample is one lifetime summary (LOINC 34133-9), and a question "
    "with no matching source tuple is refused."
)
REFUSE_EXTERNAL = (
    "Refused. openFDA, regulatory labels, and external claims are outside this demo. "
    "They are not loaded, and this page will not cite them."
)
REFUSE_TREATMENT = (
    "Refused. This demo does not give treatment advice, a care recommendation, "
    "or a next action for a patient."
)
REFUSE_NO_CITATION = (
    "Refused. No citation tuple matched this question. An answer needs "
    "(document_id, section_loinc, element_id) or "
    "(table, patient_id, encounter_id, code, start) from retrieved rows."
)
REFUSE_NO_WAREHOUSE = (
    "Refused. No Snowpark session is active, so no warehouse rows were retrieved "
    "and this page will not fill the answer from memory."
)
REFUSE_QUERY_FAILED = (
    "Refused. The warehouse query failed, so no rows were cited."
)

_REFUSAL_TEXT = {
    Intent.REFUSE_MEDICATION_CHANGE: REFUSE_MEDICATION_CHANGE,
    Intent.REFUSE_DISCHARGE: REFUSE_DISCHARGE,
    Intent.REFUSE_EXTERNAL: REFUSE_EXTERNAL,
    Intent.REFUSE_TREATMENT: REFUSE_TREATMENT,
    Intent.NO_CITATION: REFUSE_NO_CITATION,
}

_ALLOWED_NEGATIONS = (
    "not a validated stratifier",
    "not a validated risk model",
    "not a probability of deterioration",
    "not a care recommendation",
    "not for care",
    "does not give treatment advice",
    "does not change a dose",
    "not a medical device",
    "not a disease count",
    "not a feature source",
    "not recalculate",
    "not retuned",
    "not quoted as the allergy",
    "not the quoted allergy",
)

_BANNED_AFTER_NEGATION = (
    "validated stratifier",
    "validated risk model",
    "probability of deterioration",
    "you should",
    "i recommend",
    "i suggest you",
    "care recommendation",
    "increase the dose",
    "change the dose",
)


def refuse(intent: Intent, text: str) -> Answer:
    """Build a refusal. The text must already say that the question was refused."""
    if not text.startswith("Refused."):
        raise ValueError("refusal text must start with Refused.")
    return Answer(
        status=AnswerStatus.REFUSED,
        intent=intent,
        text=text,
        citations=(),
        narration_allowed=False,
    )


def refusal_text_for(intent: Intent) -> str:
    """Return the stable refusal for one intent."""
    try:
        return _REFUSAL_TEXT[intent]
    except KeyError as exc:
        raise ValueError(f"{intent.value} is not a refusal intent") from exc


def combined_refusal(intents: tuple[Intent, ...]) -> Answer:
    """Refuse once, keeping every triggered rule in the text."""
    if not intents:
        raise ValueError("combined_refusal requires at least one intent")
    text = " ".join(refusal_text_for(intent) for intent in intents)
    return refuse(intents[0], text)


def has_banned_clinical_claim(text: str) -> bool:
    """True when text makes a care, validation, or dose-change claim."""
    lowered = text.lower()
    for allowed in _ALLOWED_NEGATIONS:
        lowered = lowered.replace(allowed, "")
    return any(phrase in lowered for phrase in _BANNED_AFTER_NEGATION)
