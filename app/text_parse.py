"""Parse names and dates out of a question. No clinical lookup."""

from __future__ import annotations

import re

_PERSON = re.compile(r"\b([A-Za-z]+[0-9]+)\s+([A-Za-z]+[0-9]+)\b")
_ISO_DAY = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_LONG_DAY = re.compile(
    r"\b(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+"
    r"(\d{4})\b",
    re.IGNORECASE,
)
_MONTHS = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
}


def synthea_name(question: str) -> tuple[str, str] | None:
    """Return (first, last) when the question names a Synthea-style person."""
    match = _PERSON.search(question)
    if match is None:
        return None
    return match.group(1), match.group(2)


def cited_day(question: str) -> str | None:
    """Return YYYY-MM-DD when the question names a calendar day."""
    iso = _ISO_DAY.search(question)
    if iso is not None:
        return iso.group(1)
    long_form = _LONG_DAY.search(question)
    if long_form is None:
        return None
    day, month, year = long_form.groups()
    return f"{year}-{_MONTHS[month.lower()]}-{int(day):02d}"
