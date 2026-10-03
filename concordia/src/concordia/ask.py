"""Deterministic question routing. This module does not calculate metrics."""

from __future__ import annotations

FORBIDDEN = (
    "treat missing duty as zero",
    "ignore the synthetic",
    "blend supplier and customer",
)

VERIFIED = {
    "why did outbound customer otd for mm-440 change in may 2026": "m2-hero",
    "why did mm-440 customer otd change in may 2026": "m2-hero",
    "inbound supplier otd": "m1-hero",
    "outbound customer otd": "m2-hero",
    "unit fill rate": "m3-hero",
    "landed cost per accepted unit": "m5-hero-final",
}


def normalize(question: str) -> str:
    return " ".join(question.lower().replace("?", "").split())


def route(question: str) -> dict:
    text = normalize(question)
    if any(phrase in text for phrase in FORBIDDEN):
        return {"status": "FORBIDDEN", "fixture_id": None, "reason": "POLICY_BYPASS"}
    if text in {"what is otd", "otd"}:
        return {
            "status": "CLARIFY",
            "fixture_id": None,
            "options": ["INBOUND_SUPPLIER_OTD", "OUTBOUND_CUSTOMER_OTD", "SHOW_BOTH_UNCOMBINED"],
        }
    if text == "show both uncombined":
        return {
            "status": "SHOW_BOTH",
            "fixture_id": None,
            "fixture_ids": ["m1-hero", "m2-hero"],
            "reason": None,
        }
    if "fill rate" in text and "unit" not in text:
        return {"status": "CLARIFY", "fixture_id": None, "options": ["UNIT_FILL_RATE"]}
    if text in {"what is cost", "cost"} or text.startswith("what is the cost"):
        return {"status": "CLARIFY", "fixture_id": None, "options": ["LANDED_COST_PER_ACCEPTED_UNIT"]}
    if any(phrase in text for phrase in ("predict", "forecast", "next quarter", "optimiz")):
        return {"status": "ABSTAIN", "fixture_id": None, "reason": "UNSUPPORTED"}
    fixture_id = VERIFIED.get(text)
    if fixture_id:
        return {"status": "ANSWER", "fixture_id": fixture_id, "reason": None}
    return {"status": "ABSTAIN", "fixture_id": None, "reason": "UNVERIFIED_QUESTION"}
