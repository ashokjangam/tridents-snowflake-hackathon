# TRidents — Patient and Member 360 Clinical Document Copilot

**Snowflake CoCo CLI Hackathon 2026 — GCC Edition · Problem Statement 04**

**Team:** Sainath Chakravadhanula · Navneet Kumar · Sidharth Sampathi Rao · Ashok Jangam

A cited member chart in Snowflake: every supported answer points to the exact warehouse row or clinical-document cell behind it; unsupported or treatment-changing questions are refused.

## Submission at a glance

| Item | Location |
| --- | --- |
| Application | `PATIENT_360.CORE.PATIENT_360_APP` (Streamlit in Snowflake) |
| Full technical guide | [`docs/patient-360-a-to-z.html`](docs/patient-360-a-to-z.html) |
| Reproducible bootstrap | [`scripts/bootstrap_synthea.py`](scripts/bootstrap_synthea.py) + [`scripts/Invoke-Patient360Load.ps1`](scripts/Invoke-Patient360Load.ps1) |
| CoCo workflow evidence | [`coco/`](coco/) |
| Validation gates | [`tests/expected_checks.sql`](tests/expected_checks.sql) and [`app/tests/`](app/tests/) |
| Deployment definition | [`snowflake.yml`](snowflake.yml) |

> **Scope:** synthetic Synthea clinical records only; read-only; not for care. The primary answer path is deterministic and citation-enforced. Optional `AI_COMPLETE` narration is accepted only if all citations and clinical guardrails remain intact.

## Solution overview

One Streamlit-in-Snowflake clinical document copilot over the paired MITRE Synthea sample
(108 simulated Massachusetts patients, CSV plus C-CDA). Problem 04 permits clinical or
regulatory documents; this implementation deliberately uses the clinical path. Every displayed
answer cites warehouse rows or it refuses.

The primary outcome is cited evidence retrieval across chart, document, claim, encounter, and
coverage records. The frozen point count is a secondary descriptive cohort audit, not a validated
risk model.

## Supported cited questions

| Evidence path | Example |
| --- | --- |
| Member + encounter | `Show this member's chart summary and recent encounters.` |
| Conditions + C-CDA Problems | `Which conditions are recorded for this member, and where are they written?` |
| Medication + C-CDA Medications | `Show this member's medication list with source evidence.` |
| Allergy guard | `What allergy is recorded for that patient on 18 June 2005?` |
| Care plan + Plan of Care | `Show the care plans for this member with cited evidence.` |
| Laboratory | `What are this member's latest laboratory results?` |
| Procedure / immunization | `Which procedures are recorded for this member?` |
| Claim + encounter | `Show claims tied to encounters for this member.` |
| Payer span | `Show payer coverage spans for this member.` |

Treatment changes, absent discharge notes, external claims, and regulatory labels remain hard
refusals because those sources are not in this clinical-document build.

## What the page shows

- A synthetic, non-clinical banner (Synthea, MITRE, Walonoski et al., JAMIA 2018, plus SNOMED CT, LOINC, and RxNorm as separate terminology licenses).
- A patient selector and a profile limited to name, gender, birth, death, city, state, and the patient UUID.
- Encounter class counts, the latest 15 encounters, conditions, medications, a laboratory count plus the latest 25 laboratory rows, claim and claim-line counts, one claim whose appointment id equals an encounter id, and coverage spans.
- Deterministic answers for the frozen questions, each with a citation tuple.
- An allergy guard: the quoted code is the `allergies.csv` code on the retrieved row. Another code in the same allergy section may be shown only as not quoted.
- A point-count panel read from `PATIENT_360.CORE.RISK_SCORE`. Counts and rates on screen are the values the view returned.
- Hard refusals for a medication change, a discharge summary or progress note, openFDA or external claims, and treatment advice.

Empty member ids, stops, reactions, and encounter ids stay empty. The patient UUID is the member key.

## What the page will not do

- Change a dose, start or stop a medication, or present a row as an order.
- Quote a 2019 discharge summary, a progress note, or any encounter-scoped document. Each C-CDA here is one lifetime summary, LOINC `34133-9`.
- Call openFDA, cite a regulatory label, or cite external claims.
- Give treatment advice or a care recommendation.
- Call the point count a validated stratifier, a probability of deterioration, or a care recommendation.
- Recalculate or retune the four risk points. `CORE.RISK_SCORE` owns that arithmetic.
- Read C-CDA text as a risk feature.
- Select `SSN`, `DRIVERS`, or `PASSPORT`.
- Fill a blank `MEMBER_ID`.
- Answer from memory when Snowpark has no active session. Refusal questions still run, because they do not need a row.
- Require `AI_COMPLETE`. Narration is off unless someone turns it on, and a narration that drops a citation or breaks a guard is discarded.

## Layout

| Path | Role |
| --- | --- |
| `app/` | Intent, guardrails, citation checks, answer text, and SQL strings. Pure functions. No Streamlit and no Snowpark. |
| `app/tests/` | Standard-library unit tests, including formatter fixtures taken from the on-disk Synthea rows. The page does not load those fixtures. |
| `streamlit/patient_360.py` | The single page. It opens the active Snowpark session, runs the SQL, and calls `app`. |
| `streamlit/environment.yml` | Streamlit in Snowflake dependencies. |
| `coco/` | Evidence checklist and pasteable prompts for planning, development, execution, and testing. |

`app/queries.py` is the contract for view names and columns. A view that uses other names will fail the query, and the page shows that failure instead of substituting rows.

## How an answer is produced

1. `classify_intent` labels the question. A medication change, missing document, external source, or treatment question is a refusal even if chart rows were passed in.
2. `retrieval_steps` names the warehouse statements. A refusal has none.
3. The page runs those statements with bind parameters. Question text is not concatenated into SQL.
4. `assemble_answer` builds the sentence from the returned fields, or refuses when the row set is empty, ambiguous, or missing a citation field.
5. If the optional narration box is on, `AI_COMPLETE` receives only that question, those rows, and the citation strings, with temperature 0. `accept_narration` keeps the model text only when every citation tuple is still present, quoted codes remain, rejected codes stay negated, and the clinical-claim check passes.

Citation forms:

- Document: `(document_id, section_loinc, element_id)`. An element id without the document id is invalid, because element ids restart across files.
- Table: `(table, patient_id, encounter_id, code, start)`.
- Cohort, only for `RISK_SCORE`: `(table, index_date, horizon_end, score)`. The cohort question has no patient row, and the page does not invent one.

## Frozen questions

1. Which antihistamine is on Alexandra16 Mosciski958's medication list, and where is it written?
2. What allergy is recorded for that patient on 18 June 2005?
3. How many patients in the frozen 2023 cohort had an emergency or inpatient encounter in 2023, and how did the point count sort them?
4. Change the fexofenadine dose.
5. Quote the 2019 discharge summary.
6. What does the openFDA label say?

The page also refuses "What do the external claims show?" and "What should we do about this patient?"

Question 2 uses the selected patient ("that patient") and the day named in the question. Question 1 resolves the Synthea-style name through `CORE.PATIENT` and then keeps a single fexofenadine or antihistamine row. Zero rows or more than one row is a refusal. The worked patient id `37549f60-b5a3-69cd-dea6-5a71c4bc23cf` is only the selector default when the patient query returns it.

The allergy section query loads every `DOCUMENT_SECTION` row for that patient with LOINC `48765-2`. Citations are limited to elements whose code matches the allergy row. Any other code in that retrieval is labeled not quoted.

## `CORE` view contract

Database `PATIENT_360`, schema `CORE`. Warehouse size XS. Suggested warehouse name `PATIENT_360_WH`. Do not point this page at a maintenance app or its semantic view.

`RISK_SCORE` stores percents (`EVENT_RATE_PCT`, `BASE_RATE_PCT`). The risk query divides by 100, so the page receives fractions from 0 through 1 (`0.1443` displays as 14.43%); a fraction above 1 is refused. The query also joins the `GE_2` bucket and the `RISK_COHORT` index and horizon onto each score row, so every score row must agree. `EVENT_RATE` may be null only when `PATIENT_COUNT` is 0.

| View | View columns the page reads (`AS` = name the page receives) |
| --- | --- |
| `PATIENT` | `PATIENT_ID`, `FIRST_NAME`, `LAST_NAME`, `GENDER`, `BIRTHDATE`, `DEATHDATE`, `CITY`, `STATE` |
| `ENCOUNTER` | `ENCOUNTER_ID`, `PATIENT_ID`, `START_TS`, `STOP_TS`, `ENCOUNTER_CLASS`, `CODE`, `DESCRIPTION` |
| `CONDITION` | `PATIENT_ID`, `START_DATE AS START_TS`, `STOP_DATE AS STOP_TS`, `ENCOUNTER_ID`, `CODE`, `DESCRIPTION` |
| `MEDICATION` | `PATIENT_ID`, `ENCOUNTER_ID`, `START_TS`, `STOP_TS`, `CODE`, `DESCRIPTION`, `DISPENSES` |
| `OBSERVATION` | `PATIENT_ID`, `CATEGORY`, `OBSERVATION_TS AS OBSERVED_AT`, `ENCOUNTER_ID`, `CODE`, `DESCRIPTION`, `VALUE_TEXT AS VALUE`, `UNITS` |
| `ALLERGY` | `PATIENT_ID`, `ENCOUNTER_ID`, `START_DATE AS START`, `CODE`, `DESCRIPTION`, `REACTION_1_CODE AS REACTION1`, `REACTION_1_DESCRIPTION AS DESCRIPTION1`, `REACTION_1_SEVERITY AS SEVERITY1` |
| `CLAIM` | `CLAIM_ID`, `PATIENT_ID`, `APPOINTMENT_ID`, `DIAGNOSIS_1 AS DIAGNOSIS1`, `SERVICE_TS AS SERVICE_DATE` |
| `CLAIM_LINE` | `PATIENT_ID` |
| `MEMBER_COVERAGE` | `PATIENT_ID`, `START_TS AS START_DATE`, `END_TS AS END_DATE`, `MEMBER_ID`, `PAYER_ID`, `PAYER_NAME` |
| `DOCUMENT_SECTION` | `DOCUMENT_ID`, `PATIENT_ID`, `SECTION_LOINC`, `SECTION_TITLE`, `ELEMENT_ID`, `TEXT`, `CODE` |
| `RISK_SCORE` + `RISK_COHORT` | `SCORE_BUCKET AS SCORE`, `PATIENT_COUNT`, `EVENT_RATE_PCT / 100 AS EVENT_RATE`, `COHORT_PATIENT_COUNT AS COHORT_N`, `COHORT_EVENT_COUNT AS EVENT_N`, `BASE_RATE_PCT / 100 AS BASE_RATE`, `GE2_PATIENT_COUNT`, `GE2_EVENT_RATE`, `INDEX_DATE`, `HORIZON_END`, `EXCLUDED_DEAD`, `EXCLUDED_BORN` |

CSV names the views alias: `patients.Id` to `PATIENT_ID`, `FIRST`/`LAST` to `FIRST_NAME`/`LAST_NAME`, `encounters.Id` to `ENCOUNTER_ID`, `ENCOUNTERCLASS` to `ENCOUNTER_CLASS`, `claims.PATIENTID` to `PATIENT_ID`, `APPOINTMENTID` to `APPOINTMENT_ID`, `claims_transactions.PATIENTID` to `CLAIM_LINE.PATIENT_ID`. `MEMBER_COVERAGE` is `payer_transitions` left-joined to `payers.NAME`. `MEMBER_ID` stays null when the source span has none. `DOCUMENT_SECTION.DOCUMENT_ID` and `PATIENT_ID` are the same Synthea UUID. `CODE` on a section should be the narrative code that matches the CSV, not the first code attribute in a C-CDA entry.

`RISK_SCORE` implements the frozen points and does not retune them: age at the 2023-01-01 index at least 65; at least one prior emergency or inpatient encounter; at least 8 conditions active at the index; last prior Hemoglobin A1c (LOINC `4548-4`) at least 6.5. Features are CSV timestamps before the index. The C-CDA is not in that view. The page repeats those rules as labels and reads the numbers from the view.

The page does not query a semantic view. SQL on these objects is the citation path. Cortex Search is not required.

## Local tests

From `patient-360`:

```text
python -m unittest discover -s app/tests -t . -v
```

The tests use the Python standard library only. They check the frozen questions, refusals (including a dose change that is handed real medication rows), citation completeness, the allergy-code guard, risk wording that echoes whatever cohort the rows contain, narration accept/reject, and that the SQL strings omit identifier columns and bind patient values.

A passing unit test does not prove the warehouse load. Compare live query counts with the inspection checks below. If they disagree, the queried count is what the page will show, and the load is wrong until it is fixed.

## Deploy

From this directory, with Python 3.10+ and a Snowflake CLI connection named `patient360`
(ACCOUNTADMIN or a role that can create the database and roles):

```text
python scripts/bootstrap_synthea.py
powershell -File scripts/Invoke-Patient360Load.ps1 -Load
snow streamlit deploy --replace -c patient360
snow sql -c patient360 -f sql/95_app_grants.sql
```

The bootstrap downloads the exact paired MITRE archives, verifies their pinned SHA-256
hashes, extracts them into ignored `data/`, and runs the C-CDA parser. The PowerShell
runner expands local file URIs into ignored `generated/20_load.generated.sql`; it then
runs setup, all 18 CSV loads, C-CDA load, views, grants, expected gates, and rehearsal SQL.
An expected-check failure makes Snowflake CLI exit non-zero. No path replacement is manual.

`snowflake.yml` deploys `CORE.PATIENT_360_APP` on warehouse `PATIENT_360_WH`. The stage keeps `streamlit/patient_360.py` with `app/` and `environment.yml` at the root; the page finds `app/` in its parent directory. The app runs on the Python 3.11 container runtime.

Teammates get the analyst role, which reads `CORE` and the app but not `RAW`.
`CORE.PATIENT` also omits direct identifiers, street/ZIP, precise geolocation, and
income/expense fields:

```text
CREATE USER <teammate> PASSWORD = '<temporary>' MUST_CHANGE_PASSWORD = TRUE
    DEFAULT_ROLE = PATIENT_360_ANALYST DEFAULT_WAREHOUSE = PATIENT_360_WH;
GRANT ROLE PATIENT_360_ANALYST TO USER <teammate>;
```

`AI_COMPLETE` uses the model typed on the page. The default text is `llama3.1-70b`. Trial accounts reject `AI_COMPLETE` (error 399258), and a model may be absent in-region; in either case leave narration off. A failed call leaves the deterministic answer in place.

## Inspection checks to compare

These are the measured checks from the dataset inspection. They are not rows this app inserts. Rehearsal uses the live query. A mismatch stops the demo until the load is corrected.

| Check | Expected |
| --- | --- |
| Patients, distinct `Id` | 108 |
| Encounters, distinct `Id`, patient orphans | 5,571 and 0 |
| Claims, distinct `Id`, patient and appointment orphans | 9,421 and 0 |
| Claim lines, distinct `Id`, claim orphans | 85,047 and 0 |
| Conditions / medications / observations / procedures | 3,517 / 3,850 / 68,648 / 15,884 |
| Observations with blank encounter and blank category | 3,060, the same rows |
| Distinct `DOCUMENT_SECTION.document_id` equal to `patients.Id` | 108, mismatches 0 |
| Narrative cells reconciled to CSV | medications 3,850; conditions 3,517; encounters 5,571; procedures 15,884; immunizations 1,549; care plans 349; allergies 105 |
| Analyst `SELECT` of `SSN`, `DRIVERS`, `PASSPORT` | denied |

Question 1, when the load matches the files: Fexofenadine hydrochloride 60 MG Oral Tablet; code `997501`; start `2005-06-18T13:48:14Z`; document `37549f60-b5a3-69cd-dea6-5a71c4bc23cf`; section LOINC `10160-0`; elements `medications-desc-2` and `medications-code-2`; one medication row; encounter `37549f60-b5a3-69cd-bd30-c7a0b0133ccf`.

Question 2: quoted code `609328004`, Allergic disposition, start `2005-06-18`, that same encounter. Code `419199007` may appear only as not the quoted allergy.

Question 3, when `RISK_SCORE` matches the frozen measurement: cohort 97, events 14, base rate 14.43%, scores 0/1/2/3/4 = 19/37/35/6/0 patients, rates 5.26%, 16.22%, 14.29%, 33.33%, and no rate on the zero-patient score, score 2 or higher = 41 patients at 17.07%. The sentence on screen is that score 2 sits below score 1 when the retrieved rates say so.

## Sources

Synthea sample CSV and C-CDA from MITRE SyntheticMass, paired export, local copies under `data/csv/` and `data/ccda/`. MITRE states the synthetic data may be used without restriction for secondary uses. The generator is Apache-2.0. Citation: Jason Walonoski et al., JAMIA 25(3), 2018, 230–238, https://doi.org/10.1093/jamia/ocx079. SNOMED CT, LOINC, and RxNorm keep their own licenses.

## Cuts

No model training, no retuned points, no openFDA load, no FHIR zip, no imaging pixels, no generated notes, no filled-in member ids, no treatment sentence, and no sentence that calls the point count a validated model. Drop Cortex Search before the SQL citation. Drop Cortex narration before the view, the bucket table, and the refusals.
