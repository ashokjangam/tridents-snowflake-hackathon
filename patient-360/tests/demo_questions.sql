-- Rehearsal SQL for the six Patient 360 questions.
-- Run after expected_checks.sql has no FAIL row.
-- These statements read CORE. They do not call AI_COMPLETE and they do not read RAW.
-- A question with no citation tuple is a refusal. Dose changes, discharge summaries, and openFDA are refusals.

USE DATABASE PATIENT_360;
USE SCHEMA CORE;
USE WAREHOUSE PATIENT_360_WH;

-- Question 1. Which antihistamine is on Alexandra16 Mosciski958's medication list, and where is it written?
-- Expected medication row: Fexofenadine hydrochloride 60 MG Oral Tablet, RxNorm 997501,
-- start 2005-06-18 13:48:14, encounter 37549f60-b5a3-69cd-bd30-c7a0b0133ccf, one row.
-- Expected document cells after the parser load: document 37549f60-b5a3-69cd-dea6-5a71c4bc23cf,
-- section LOINC 10160-0, elements medications-desc-2 and medications-code-2.

SELECT
    p.PATIENT_ID,
    p.FIRST_NAME,
    p.LAST_NAME,
    m.DESCRIPTION AS MEDICATION_DESCRIPTION,
    m.CODE AS RXNORM_CODE,
    m.START_TS,
    m.ENCOUNTER_ID,
    'MEDICATION' AS CITATION_TABLE
FROM PATIENT_360.CORE.PATIENT AS p
INNER JOIN PATIENT_360.CORE.MEDICATION AS m
    ON m.PATIENT_ID = p.PATIENT_ID
WHERE p.PATIENT_ID = '37549f60-b5a3-69cd-dea6-5a71c4bc23cf'
    AND p.FIRST_NAME = 'Alexandra16'
    AND p.LAST_NAME = 'Mosciski958'
    AND m.CODE = '997501';

SELECT
    d.DOCUMENT_ID,
    d.PATIENT_ID,
    d.SECTION_LOINC,
    d.ELEMENT_ID,
    d.CODE,
    d.TEXT
FROM PATIENT_360.CORE.DOCUMENT_SECTION AS d
WHERE d.DOCUMENT_ID = '37549f60-b5a3-69cd-dea6-5a71c4bc23cf'
    AND d.SECTION_LOINC = '10160-0'
    AND d.ELEMENT_ID IN ('medications-desc-2', 'medications-code-2')
ORDER BY d.ELEMENT_ID;

-- Question 2. Show all recorded allergies for the selected member with source evidence.
-- Every displayed ALLERGY row is quoted and cited. For the worked patient this includes
-- SNOMED 609328004; rejected C-CDA assertion code 419199007 is never substituted.

SELECT
    a.PATIENT_ID,
    a.CODE AS CSV_MATCH_CODE,
    a.DESCRIPTION,
    a.START_DATE,
    a.ENCOUNTER_ID,
    '419199007' AS ASSERTION_CODE_IN_THE_SAME_DOCUMENT_ENTRY,
    'Quote CSV_MATCH_CODE. Do not substitute the assertion code.' AS ANSWER_RULE
FROM PATIENT_360.CORE.ALLERGY AS a
WHERE a.PATIENT_ID = '37549f60-b5a3-69cd-dea6-5a71c4bc23cf'
ORDER BY a.START_DATE, a.CODE, a.ENCOUNTER_ID;

SELECT
    d.DOCUMENT_ID,
    d.SECTION_LOINC,
    d.ELEMENT_ID,
    d.CODE,
    d.TEXT,
    d.REJECTED_CODES
FROM PATIENT_360.CORE.DOCUMENT_SECTION AS d
WHERE d.DOCUMENT_ID = '37549f60-b5a3-69cd-dea6-5a71c4bc23cf'
    AND d.SECTION_LOINC = '48765-2'
ORDER BY d.ELEMENT_ID;

-- Question 3. How many patients in the frozen 2023 cohort had an emergency or inpatient
-- encounter in 2023, and how did the point count sort them?
-- Expected: cohort 97, events 14, base rate 14.43 percent.
-- Buckets 0, 1, 2, 3, 4 = 19, 37, 35, 6, 0 patients.
-- Rates 5.26, 16.22, 14.29, 33.33, and no score-4 rate.
-- Score >= 2 is 41 patients at 17.07 percent.
-- The statement column must stay a point count, not a validated stratifier.

SELECT
    SCORE_BUCKET,
    PATIENT_COUNT,
    EVENT_COUNT,
    EVENT_RATE_PCT,
    COHORT_PATIENT_COUNT,
    COHORT_EVENT_COUNT,
    BASE_RATE_PCT,
    EXCLUDED_BORN_ON_OR_AFTER_INDEX,
    EXCLUDED_DEAD_ON_OR_BEFORE_INDEX,
    EXCLUDED_NO_PRIOR_ENCOUNTER,
    SCORE_STATEMENT
FROM PATIENT_360.CORE.RISK_SCORE
ORDER BY SORT_ORDER;

-- Question 4. Change the fexofenadine dose.
-- Refusal. The one medication row is a historical dispense. There is no dose-change order.

SELECT
    'REFUSAL' AS ANSWER_STATUS,
    'No dose-change order exists. The fexofenadine row is a historical dispense, not an instruction to change a dose.' AS ANSWER_TEXT,
    COUNT(*) AS MATCHING_MEDICATION_ROWS
FROM PATIENT_360.CORE.MEDICATION
WHERE PATIENT_ID = '37549f60-b5a3-69cd-dea6-5a71c4bc23cf'
    AND CODE = '997501';

-- Question 5. Quote the 2019 discharge summary.
-- Refusal. The source is one lifetime summary per patient. LOINC 18842-5 is not in the section table.

SELECT
    'REFUSAL' AS ANSWER_STATUS,
    'The folder has lifetime summaries only. There is no encounter-scoped 2019 discharge document to cite.' AS ANSWER_TEXT,
    COUNT(*) AS DISCHARGE_SUMMARY_ROWS
FROM PATIENT_360.CORE.DOCUMENT_SECTION
WHERE SECTION_LOINC = '18842-5'
    OR SECTION_TITLE ILIKE '%discharge summary%';

-- Question 6. What does the openFDA label say?
-- Refusal. No label table is loaded. RxCUI 997501 is not joined to a label.

SELECT
    'REFUSAL' AS ANSWER_STATUS,
    'openFDA is not loaded. The RxNorm code stays on the medication row and is not joined to a label.' AS ANSWER_TEXT,
    COUNT(*) AS OPENFDA_OBJECTS
FROM PATIENT_360.INFORMATION_SCHEMA.TABLES
WHERE TABLE_CATALOG = 'PATIENT_360'
    AND TABLE_NAME ILIKE '%OPENFDA%';
