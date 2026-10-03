"""The verified question catalog as declared on the semantic view (no Snowflake dependency, so tests can import it)."""

from __future__ import annotations

import re


def verified_queries(text: str) -> list[tuple[str, str, str]]:
    """(QUESTION_ID, question, SQL) for each AI_VERIFIED_QUERIES entry; vq_07 maps to VQ-07."""
    found = re.findall(r"\bvq_(\d\d) AS \(QUESTION '([^']+)'.*?SQL\s+'((?:[^']|'')*)'", text, flags=re.S)
    return [(f"VQ-{num}", question, statement.replace("''", "'")) for num, question, statement in found]
