"""SQL against PATIENT_360.CORE. The page binds parameters and runs these strings."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.constants import DATABASE, SCHEMA

_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_]*")


def _qualified(name: str) -> str:
    if _IDENTIFIER.fullmatch(name) is None:
        raise ValueError(f"unexpected object name: {name}")
    return f"{DATABASE}.{SCHEMA}.{name}"


@dataclass(frozen=True, slots=True)
class QuerySpec:
    """One bind-parameterized statement."""

    name: str
    sql: str
    params: tuple[str, ...] = ()


def patient_list_query() -> QuerySpec:
    table = _qualified("PATIENT")
    return QuerySpec(
        name="patient_list",
        sql=f"""
SELECT
    PATIENT_ID,
    FIRST_NAME,
    LAST_NAME,
    GENDER,
    BIRTHDATE,
    DEATHDATE,
    CITY,
    STATE
FROM {table}
ORDER BY LAST_NAME, FIRST_NAME, PATIENT_ID
""".strip(),
    )


def patient_name_query(first_name: str, last_name: str) -> QuerySpec:
    table = _qualified("PATIENT")
    return QuerySpec(
        name="patient_name",
        sql=f"""
SELECT
    PATIENT_ID,
    FIRST_NAME,
    LAST_NAME,
    GENDER,
    BIRTHDATE,
    DEATHDATE,
    CITY,
    STATE
FROM {table}
WHERE FIRST_NAME = ? AND LAST_NAME = ?
""".strip(),
        params=(first_name, last_name),
    )


def encounter_count_query(patient_id: str) -> QuerySpec:
    table = _qualified("ENCOUNTER")
    return QuerySpec(
        name="encounter_counts",
        sql=f"""
SELECT ENCOUNTER_CLASS, COUNT(*) AS ENCOUNTER_COUNT
FROM {table}
WHERE PATIENT_ID = ?
GROUP BY ENCOUNTER_CLASS
ORDER BY ENCOUNTER_COUNT DESC, ENCOUNTER_CLASS
""".strip(),
        params=(patient_id,),
    )


def encounter_query(patient_id: str) -> QuerySpec:
    table = _qualified("ENCOUNTER")
    return QuerySpec(
        name="encounters",
        sql=f"""
SELECT
    ENCOUNTER_ID,
    START_TS,
    STOP_TS,
    ENCOUNTER_CLASS,
    CODE,
    DESCRIPTION
FROM {table}
WHERE PATIENT_ID = ?
ORDER BY START_TS DESC
LIMIT 15
""".strip(),
        params=(patient_id,),
    )


def condition_query(patient_id: str) -> QuerySpec:
    table = _qualified("CONDITION")
    return QuerySpec(
        name="conditions",
        sql=f"""
SELECT START_DATE AS START_TS, STOP_DATE AS STOP_TS, ENCOUNTER_ID, CODE, DESCRIPTION
FROM {table}
WHERE PATIENT_ID = ?
ORDER BY START_DATE, CODE
""".strip(),
        params=(patient_id,),
    )


def medication_panel_query(patient_id: str) -> QuerySpec:
    table = _qualified("MEDICATION")
    return QuerySpec(
        name="medications",
        sql=f"""
SELECT START_TS, STOP_TS, ENCOUNTER_ID, CODE, DESCRIPTION, DISPENSES
FROM {table}
WHERE PATIENT_ID = ?
ORDER BY START_TS, CODE
""".strip(),
        params=(patient_id,),
    )


def antihistamine_query(patient_id: str) -> QuerySpec:
    table = _qualified("MEDICATION")
    return QuerySpec(
        name="antihistamine",
        sql=f"""
SELECT
    PATIENT_ID,
    ENCOUNTER_ID,
    START_TS AS "START",
    CODE,
    DESCRIPTION
FROM {table}
WHERE PATIENT_ID = ?
  AND (
        UPPER(DESCRIPTION) LIKE '%FEXOFENADINE%'
     OR UPPER(DESCRIPTION) LIKE '%ANTIHISTAMINE%'
  )
""".strip(),
        params=(patient_id,),
    )


def medication_section_query(patient_id: str, code: str, description: str) -> QuerySpec:
    table = _qualified("DOCUMENT_SECTION")
    return QuerySpec(
        name="medication_section",
        sql=f"""
SELECT
    DOCUMENT_ID,
    PATIENT_ID,
    SECTION_LOINC,
    SECTION_TITLE,
    ELEMENT_ID,
    TEXT,
    CODE
FROM {table}
WHERE PATIENT_ID = ?
  AND SECTION_LOINC = '10160-0'
  AND (
        CODE = ?
     OR CODE LIKE '%' || ? || '%' ESCAPE '\\\\'
     OR UPPER(TEXT) LIKE '%' || UPPER(?) || '%' ESCAPE '\\\\'
  )
""".strip(),
        params=(patient_id, code, _like_literal(code), _like_literal(description)),
    )


def lab_count_query(patient_id: str) -> QuerySpec:
    table = _qualified("OBSERVATION")
    return QuerySpec(
        name="lab_count",
        sql=f"""
SELECT COUNT(*) AS LAB_COUNT
FROM {table}
WHERE PATIENT_ID = ? AND LOWER(CATEGORY) = 'laboratory'
""".strip(),
        params=(patient_id,),
    )


def lab_query(patient_id: str) -> QuerySpec:
    table = _qualified("OBSERVATION")
    return QuerySpec(
        name="labs",
        sql=f"""
SELECT OBSERVATION_TS AS OBSERVED_AT, ENCOUNTER_ID, CODE, DESCRIPTION, VALUE_TEXT AS "VALUE", UNITS
FROM {table}
WHERE PATIENT_ID = ? AND LOWER(CATEGORY) = 'laboratory'
ORDER BY OBSERVATION_TS DESC
LIMIT 25
""".strip(),
        params=(patient_id,),
    )


def claim_count_query(patient_id: str) -> QuerySpec:
    table = _qualified("CLAIM")
    return QuerySpec(
        name="claim_count",
        sql=f"""
SELECT COUNT(*) AS CLAIM_COUNT
FROM {table}
WHERE PATIENT_ID = ?
""".strip(),
        params=(patient_id,),
    )


def claim_line_count_query(patient_id: str) -> QuerySpec:
    table = _qualified("CLAIM_LINE")
    return QuerySpec(
        name="claim_line_count",
        sql=f"""
SELECT COUNT(*) AS LINE_COUNT
FROM {table}
WHERE PATIENT_ID = ?
""".strip(),
        params=(patient_id,),
    )


def claim_encounter_query(patient_id: str) -> QuerySpec:
    claim = _qualified("CLAIM")
    encounter = _qualified("ENCOUNTER")
    return QuerySpec(
        name="claim_on_encounter",
        sql=f"""
SELECT
    c.CLAIM_ID,
    c.APPOINTMENT_ID,
    e.ENCOUNTER_ID,
    c.DIAGNOSIS_1 AS DIAGNOSIS1,
    c.SERVICE_TS AS SERVICE_DATE
FROM {claim} AS c
INNER JOIN {encounter} AS e
    ON c.APPOINTMENT_ID = e.ENCOUNTER_ID
   AND c.PATIENT_ID = e.PATIENT_ID
WHERE c.PATIENT_ID = ?
ORDER BY c.SERVICE_TS, c.CLAIM_ID
LIMIT 1
""".strip(),
        params=(patient_id,),
    )


def coverage_query(patient_id: str) -> QuerySpec:
    table = _qualified("MEMBER_COVERAGE")
    return QuerySpec(
        name="coverage",
        sql=f"""
SELECT START_TS AS START_DATE, END_TS AS END_DATE, MEMBER_ID, PAYER_ID, PAYER_NAME
FROM {table}
WHERE PATIENT_ID = ?
ORDER BY START_TS
""".strip(),
        params=(patient_id,),
    )


def allergy_query(patient_id: str) -> QuerySpec:
    table = _qualified("ALLERGY")
    return QuerySpec(
        name="allergy",
        sql=f"""
SELECT
    PATIENT_ID,
    ENCOUNTER_ID,
    START_DATE AS "START",
    CODE,
    DESCRIPTION,
    REACTION_1_CODE AS REACTION1,
    REACTION_1_DESCRIPTION AS DESCRIPTION1,
    REACTION_1_SEVERITY AS SEVERITY1
FROM {table}
WHERE PATIENT_ID = ?
ORDER BY START_DATE, CODE, ENCOUNTER_ID
""".strip(),
        params=(patient_id,),
    )


def allergy_section_query(patient_id: str) -> QuerySpec:
    """Load the whole allergy section so a second code can be seen and not quoted."""
    table = _qualified("DOCUMENT_SECTION")
    return QuerySpec(
        name="allergy_section",
        sql=f"""
SELECT
    DOCUMENT_ID,
    PATIENT_ID,
    SECTION_LOINC,
    SECTION_TITLE,
    ELEMENT_ID,
    TEXT,
    CODE,
    REJECTED_CODES
FROM {table}
WHERE PATIENT_ID = ?
  AND SECTION_LOINC = '48765-2'
""".strip(),
        params=(patient_id,),
    )


def member_summary_query(patient_id: str) -> QuerySpec:
    table = _qualified("PATIENT")
    return QuerySpec(
        name="member_summary",
        sql=f"""
SELECT PATIENT_ID, FIRST_NAME, LAST_NAME, GENDER, BIRTHDATE, DEATHDATE, CITY, STATE
FROM {table}
WHERE PATIENT_ID = ?
""".strip(),
        params=(patient_id,),
    )


def recent_encounter_query(patient_id: str) -> QuerySpec:
    table = _qualified("ENCOUNTER")
    return QuerySpec(
        name="recent_encounters",
        sql=f"""
SELECT PATIENT_ID, ENCOUNTER_ID, START_TS AS "START", STOP_TS, ENCOUNTER_CLASS,
       CODE, DESCRIPTION
FROM {table}
WHERE PATIENT_ID = ?
ORDER BY START_TS DESC
LIMIT 5
""".strip(),
        params=(patient_id,),
    )


def condition_evidence_query(patient_id: str) -> QuerySpec:
    table = _qualified("CONDITION")
    return QuerySpec(
        name="condition_evidence",
        sql=f"""
SELECT PATIENT_ID, ENCOUNTER_ID, START_DATE AS "START", STOP_DATE,
       CODE, DESCRIPTION
FROM {table}
WHERE PATIENT_ID = ?
ORDER BY IFF(STOP_DATE IS NULL, 1, 0) DESC, START_DATE DESC
LIMIT 10
""".strip(),
        params=(patient_id,),
    )


def medication_evidence_query(patient_id: str) -> QuerySpec:
    table = _qualified("MEDICATION")
    return QuerySpec(
        name="medication_evidence",
        sql=f"""
SELECT PATIENT_ID, ENCOUNTER_ID, START_TS AS "START", STOP_TS,
       CODE, DESCRIPTION, DISPENSES
FROM {table}
WHERE PATIENT_ID = ?
ORDER BY START_TS DESC, CODE
LIMIT 10
""".strip(),
        params=(patient_id,),
    )


def care_plan_evidence_query(patient_id: str) -> QuerySpec:
    table = _qualified("CAREPLAN")
    return QuerySpec(
        name="care_plan_evidence",
        sql=f"""
SELECT PATIENT_ID, ENCOUNTER_ID, START_DATE AS "START", STOP_DATE,
       CAREPLAN_ID, CODE, DESCRIPTION, REASON_CODE, REASON_DESCRIPTION
FROM {table}
WHERE PATIENT_ID = ?
ORDER BY START_DATE DESC, CODE
LIMIT 10
""".strip(),
        params=(patient_id,),
    )


def lab_evidence_query(patient_id: str) -> QuerySpec:
    table = _qualified("OBSERVATION")
    return QuerySpec(
        name="lab_evidence",
        sql=f"""
SELECT PATIENT_ID, ENCOUNTER_ID, SOURCE_FILE_ROW_NUMBER AS ROW_ID,
       OBSERVATION_TS AS OBSERVED_AT, CODE, DESCRIPTION,
       VALUE_TEXT AS "VALUE", UNITS
FROM {table}
WHERE PATIENT_ID = ? AND LOWER(CATEGORY) = 'laboratory'
ORDER BY OBSERVATION_TS DESC, SOURCE_FILE_ROW_NUMBER DESC
LIMIT 10
""".strip(),
        params=(patient_id,),
    )


def procedure_evidence_query(patient_id: str) -> QuerySpec:
    table = _qualified("PROCEDURE")
    return QuerySpec(
        name="procedure_evidence",
        sql=f"""
SELECT PATIENT_ID, ENCOUNTER_ID, START_TS AS "START", STOP_TS,
       CODE, DESCRIPTION, REASON_CODE, REASON_DESCRIPTION
FROM {table}
WHERE PATIENT_ID = ?
ORDER BY START_TS DESC, CODE
LIMIT 10
""".strip(),
        params=(patient_id,),
    )


def immunization_evidence_query(patient_id: str) -> QuerySpec:
    table = _qualified("IMMUNIZATION")
    return QuerySpec(
        name="immunization_evidence",
        sql=f"""
SELECT PATIENT_ID, ENCOUNTER_ID, IMMUNIZATION_TS AS "START", CODE, DESCRIPTION
FROM {table}
WHERE PATIENT_ID = ?
ORDER BY IMMUNIZATION_TS DESC, CODE
LIMIT 10
""".strip(),
        params=(patient_id,),
    )


def claim_evidence_query(patient_id: str) -> QuerySpec:
    claim = _qualified("CLAIM")
    encounter = _qualified("ENCOUNTER")
    return QuerySpec(
        name="claim_evidence",
        sql=f"""
SELECT c.PATIENT_ID, c.CLAIM_ID, c.APPOINTMENT_ID AS ENCOUNTER_ID,
       c.SERVICE_TS AS SERVICE_DATE, c.DIAGNOSIS_1 AS DIAGNOSIS1,
       e.ENCOUNTER_CLASS, e.DESCRIPTION AS ENCOUNTER_DESCRIPTION
FROM {claim} AS c
INNER JOIN {encounter} AS e
    ON c.PATIENT_ID = e.PATIENT_ID AND c.APPOINTMENT_ID = e.ENCOUNTER_ID
WHERE c.PATIENT_ID = ?
ORDER BY c.SERVICE_TS DESC, c.CLAIM_ID
LIMIT 5
""".strip(),
        params=(patient_id,),
    )


def coverage_evidence_query(patient_id: str) -> QuerySpec:
    table = _qualified("MEMBER_COVERAGE")
    return QuerySpec(
        name="coverage_evidence",
        sql=f"""
SELECT PATIENT_ID, START_TS AS "START", END_TS AS "END",
       MEMBER_ID, PAYER_ID, PAYER_NAME
FROM {table}
WHERE PATIENT_ID = ?
ORDER BY START_TS DESC, PAYER_ID
LIMIT 10
""".strip(),
        params=(patient_id,),
    )


def document_section_query(patient_id: str, section_loinc: str) -> QuerySpec:
    table = _qualified("DOCUMENT_SECTION")
    return QuerySpec(
        name="document_section",
        sql=f"""
SELECT DOCUMENT_ID, PATIENT_ID, SECTION_LOINC, SECTION_TITLE, ELEMENT_ID, TEXT, CODE
FROM {table}
WHERE PATIENT_ID = ? AND SECTION_LOINC = ?
ORDER BY ELEMENT_ID
""".strip(),
        params=(patient_id, section_loinc),
    )


def risk_query() -> QuerySpec:
    table = _qualified("RISK_SCORE")
    cohort = _qualified("RISK_COHORT")
    return QuerySpec(
        name="risk",
        sql=f"""
WITH ge2 AS (
    SELECT PATIENT_COUNT, EVENT_RATE_PCT
    FROM {table}
    WHERE SCORE_BUCKET = 'GE_2'
),
window_dates AS (
    SELECT MIN(INDEX_DATE) AS INDEX_DATE, MIN(HORIZON_END) AS HORIZON_END
    FROM {cohort}
)
SELECT
    TO_NUMBER(s.SCORE_BUCKET) AS SCORE,
    s.PATIENT_COUNT,
    s.EVENT_COUNT AS BUCKET_EVENT_COUNT,
    s.EVENT_RATE_PCT / 100 AS EVENT_RATE,
    s.COHORT_PATIENT_COUNT AS COHORT_N,
    s.COHORT_EVENT_COUNT AS EVENT_N,
    s.BASE_RATE_PCT / 100 AS BASE_RATE,
    ge2.PATIENT_COUNT AS GE2_PATIENT_COUNT,
    ge2.EVENT_RATE_PCT / 100 AS GE2_EVENT_RATE,
    w.INDEX_DATE,
    w.HORIZON_END,
    s.EXCLUDED_DEAD_ON_OR_BEFORE_INDEX AS EXCLUDED_DEAD,
    s.EXCLUDED_BORN_ON_OR_AFTER_INDEX AS EXCLUDED_BORN
FROM {table} AS s
CROSS JOIN ge2
CROSS JOIN window_dates AS w
WHERE s.SCORE_BUCKET <> 'GE_2'
ORDER BY SCORE
""".strip(),
    )


def population_query() -> QuerySpec:
    """One row of sample size. The page does not recompute risk here."""
    patient = _qualified("PATIENT")
    encounter = _qualified("ENCOUNTER")
    claim = _qualified("CLAIM")
    document = _qualified("DOCUMENT_SECTION")
    return QuerySpec(
        name="population",
        sql=f"""
SELECT
    (SELECT COUNT(*) FROM {patient}) AS MEMBER_COUNT,
    (SELECT COUNT(*) FROM {encounter}) AS ENCOUNTER_COUNT,
    (
        SELECT COUNT(*)
        FROM {claim} AS c
        INNER JOIN {encounter} AS e
            ON c.APPOINTMENT_ID = e.ENCOUNTER_ID
           AND c.PATIENT_ID = e.PATIENT_ID
    ) AS CLAIMS_ON_ENCOUNTER,
    (
        SELECT COUNT(DISTINCT d.DOCUMENT_ID)
        FROM {document} AS d
        INNER JOIN {patient} AS p
            ON d.DOCUMENT_ID = p.PATIENT_ID
    ) AS DOCUMENTS_MATCHED
""".strip(),
    )


def chart_queries(patient_id: str) -> tuple[QuerySpec, ...]:
    """Panels for one selected patient. Question SQL is separate."""
    return (
        encounter_count_query(patient_id),
        encounter_query(patient_id),
        condition_query(patient_id),
        medication_panel_query(patient_id),
        lab_count_query(patient_id),
        lab_query(patient_id),
        claim_count_query(patient_id),
        claim_line_count_query(patient_id),
        claim_encounter_query(patient_id),
        coverage_query(patient_id),
    )


def all_statement_sql() -> tuple[str, ...]:
    """Every statement template, for the identifier and injection checks."""
    sample = "00000000-0000-0000-0000-000000000000"
    specs = [
        patient_list_query(),
        patient_name_query("First1", "Last1"),
        *chart_queries(sample),
        antihistamine_query(sample),
        medication_section_query(sample, "1", "desc"),
        allergy_query(sample),
        allergy_section_query(sample),
        member_summary_query(sample),
        recent_encounter_query(sample),
        condition_evidence_query(sample),
        medication_evidence_query(sample),
        care_plan_evidence_query(sample),
        lab_evidence_query(sample),
        procedure_evidence_query(sample),
        immunization_evidence_query(sample),
        claim_evidence_query(sample),
        coverage_evidence_query(sample),
        document_section_query(sample, "11450-4"),
        risk_query(),
        population_query(),
    ]
    return tuple(spec.sql for spec in specs)


def _like_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
