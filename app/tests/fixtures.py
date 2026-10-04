"""Rows copied from the on-disk Synthea sample for formatter tests.

These fixtures exercise citation wording. The Streamlit page does not load them.
"""

from __future__ import annotations

WORKED_PATIENT_ID = "37549f60-b5a3-69cd-dea6-5a71c4bc23cf"
WORKED_ENCOUNTER_ID = "37549f60-b5a3-69cd-bd30-c7a0b0133ccf"

WORKED_PATIENT = {
    "PATIENT_ID": WORKED_PATIENT_ID,
    "FIRST_NAME": "Alexandra16",
    "LAST_NAME": "Mosciski958",
    "GENDER": "F",
    "BIRTHDATE": "1981-05-25",
    "DEATHDATE": None,
    "CITY": "Waltham",
    "STATE": "Massachusetts",
}

WORKED_MEDICATION = {
    "PATIENT_ID": WORKED_PATIENT_ID,
    "ENCOUNTER_ID": WORKED_ENCOUNTER_ID,
    "START": "2005-06-18T13:48:14Z",
    "CODE": "997501",
    "DESCRIPTION": "Fexofenadine hydrochloride 60 MG Oral Tablet",
}

WORKED_MEDICATION_SECTIONS = (
    {
        "DOCUMENT_ID": WORKED_PATIENT_ID,
        "PATIENT_ID": WORKED_PATIENT_ID,
        "SECTION_LOINC": "10160-0",
        "SECTION_TITLE": "Medications",
        "ELEMENT_ID": "medications-desc-2",
        "TEXT": "Fexofenadine hydrochloride 60 MG Oral Tablet",
        "CODE": "997501",
    },
    {
        "DOCUMENT_ID": WORKED_PATIENT_ID,
        "PATIENT_ID": WORKED_PATIENT_ID,
        "SECTION_LOINC": "10160-0",
        "SECTION_TITLE": "Medications",
        "ELEMENT_ID": "medications-code-2",
        "TEXT": "http://www.nlm.nih.gov/research/umls/rxnorm 997501",
        "CODE": "997501",
    },
)

WORKED_ALLERGY = {
    "PATIENT_ID": WORKED_PATIENT_ID,
    "ENCOUNTER_ID": WORKED_ENCOUNTER_ID,
    "START": "2005-06-18",
    "CODE": "609328004",
    "DESCRIPTION": "Allergic disposition (finding)",
    "REACTION1": None,
    "DESCRIPTION1": None,
    "SEVERITY1": None,
}

WORKED_ALLERGY_SECTIONS = (
    {
        "DOCUMENT_ID": WORKED_PATIENT_ID,
        "PATIENT_ID": WORKED_PATIENT_ID,
        "SECTION_LOINC": "48765-2",
        "ELEMENT_ID": "allergies-desc-1",
        "TEXT": "Allergic disposition (finding)",
        "CODE": "609328004",
    },
    {
        "DOCUMENT_ID": WORKED_PATIENT_ID,
        "PATIENT_ID": WORKED_PATIENT_ID,
        "SECTION_LOINC": "48765-2",
        "ELEMENT_ID": "allergies-code-1",
        "TEXT": "http://snomed.info/sct 609328004",
        "CODE": "609328004",
    },
    {
        "DOCUMENT_ID": WORKED_PATIENT_ID,
        "PATIENT_ID": WORKED_PATIENT_ID,
        "SECTION_LOINC": "48765-2",
        "ELEMENT_ID": "entry-assertion",
        "TEXT": "Allergy to substance",
        "CODE": "419199007",
    },
)


def risk_bucket(
    score: int,
    patients: int,
    rate: str | None,
    *,
    cohort: int = 97,
    events: int = 14,
    base: str = "0.1443",
    ge2_patients: int | None = 41,
    ge2_rate: str | None = "0.1707",
    excluded_dead: int | None = 7,
    excluded_born: int | None = 4,
) -> dict[str, object]:
    """One CORE.RISK_SCORE-shaped row. Rates are fractions."""
    row: dict[str, object] = {
        "SCORE": score,
        "PATIENT_COUNT": patients,
        "EVENT_RATE": rate,
        "COHORT_N": cohort,
        "EVENT_N": events,
        "BASE_RATE": base,
        "INDEX_DATE": "2023-01-01",
        "HORIZON_END": "2024-01-01",
    }
    if ge2_patients is not None:
        row["GE2_PATIENT_COUNT"] = ge2_patients
    if ge2_rate is not None:
        row["GE2_EVENT_RATE"] = ge2_rate
    if excluded_dead is not None:
        row["EXCLUDED_DEAD"] = excluded_dead
    if excluded_born is not None:
        row["EXCLUDED_BORN"] = excluded_born
    return row


INSPECTED_RISK_ROWS = (
    risk_bucket(0, 19, "0.0526"),
    risk_bucket(1, 37, "0.1622"),
    risk_bucket(2, 35, "0.1429"),
    risk_bucket(3, 6, "0.3333"),
    risk_bucket(4, 0, None),
)
