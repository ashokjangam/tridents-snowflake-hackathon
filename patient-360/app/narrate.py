"""Optional AI_COMPLETE narration bounded to rows the SQL step already returned."""

from __future__ import annotations

import json
import re

from app.citations import format_citation, rejected_code_is_guarded
from app.guardrails import has_banned_clinical_claim
from app.models import Answer, AnswerStatus

DEFAULT_AI_COMPLETE_MODEL = "llama3.1-70b"
_EMPTY_ALLERGY_SCOPE = "No allergy rows are recorded in this dataset"

NARRATION_SQL = """
SELECT AI_COMPLETE(?, ?, OBJECT_CONSTRUCT('temperature', 0)) AS NARRATION
""".strip()


def build_narration_prompt(question: str, answer: Answer, rows: list[dict[str, object]]) -> str | None:
    """Return a prompt that can only narrate the retrieved rows, or None to skip."""
    if answer.status is not AnswerStatus.CITED or not answer.narration_allowed:
        return None
    if not answer.citations or not rows:
        return None
    citations = [format_citation(citation) for citation in answer.citations]
    payload = json.dumps(rows, default=str, sort_keys=True)
    quoted = ", ".join(answer.quoted_codes) if answer.quoted_codes else "none"
    rejected = ", ".join(answer.rejected_codes) if answer.rejected_codes else "none"
    return (
        "Narrate a software demo of synthetic Synthea records. Not for care. "
        "Use only the JSON rows below. Do not add a medication, dose, label, lab, "
        "claim, or patient that is not in the rows. Do not give treatment advice. "
        "Do not call a point count a probability or a validated model. "
        "If quoted_codes is present, those are the only codes you may quote as the finding. "
        "If you mention a rejected code, the word not must appear immediately before it. "
        "If the deterministic answer says no allergy rows are recorded in this dataset, "
        "preserve that exact dataset scope and do not say the member has no allergies. "
        "End with the citation tuples exactly as given.\n\n"
        f"Question: {question}\n"
        f"quoted_codes: {quoted}\n"
        f"rejected_codes: {rejected}\n"
        f"Citations: {json.dumps(citations)}\n"
        f"Rows: {payload}\n"
    )


def accept_narration(narration: str, answer: Answer) -> bool:
    """Keep narration only when it preserves citations and the allergy guard."""
    if answer.status is not AnswerStatus.CITED or not narration.strip():
        return False
    for citation in answer.citations:
        if format_citation(citation) not in narration:
            return False
    if has_banned_clinical_claim(narration):
        return False
    if _EMPTY_ALLERGY_SCOPE in answer.text and _EMPTY_ALLERGY_SCOPE not in narration:
        return False
    for code in answer.quoted_codes:
        if code not in narration:
            return False
    for quoted in answer.quoted_codes:
        for rejected in answer.rejected_codes:
            if not rejected_code_is_guarded(narration, quoted, rejected):
                return False
    if re.search(r"\bopen\s*fda\b", narration, re.IGNORECASE):
        return False
    return True
