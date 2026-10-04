# Execution prompt

Paste this when the Snowflake account is changed. Use the already authenticated Snowflake CLI. Do not print passwords, tokens, or connection strings. Do not query or alter `PNEUMORA`, `SNOWCORE_REAL`, or `TRIDENT_OPS`.

Create or confirm:

- Database `PATIENT_360`.
- An XS warehouse. Record its name. `PATIENT_360_WH` is the name the README uses.
- Schema `RAW` loaded from `data/csv/` (18 tables) and `DOCUMENT_SECTION` parsed from `data/ccda/` (108 files). Use the pinned bootstrap; do not download another Synthea archive, the FHIR zip, imaging pixels, or openFDA.
- Schema `CORE` with the views in `patient-360/README.md`. Grant the demo role `SELECT` on `CORE` only. Do not grant `SSN`, `DRIVERS`, or `PASSPORT`.
- One Streamlit app whose stage root contains `streamlit/patient_360.py` (as `patient_360.py`), `streamlit/environment.yml`, and the `app/` package.

Record every Snowflake CLI command you ran and the query id for:

- Patient, encounter, claim, and claim-line counts, plus the orphan counts in the README table.
- `DOCUMENT_SECTION` distinct `document_id` compared with `patients.Id`.
- The question-1 medication lookup for the patient the name query returns (do not hardcode a row if the query returns none).

If a command fails, stop and record the error. Do not create a substitute row. Do not train a model. Do not retune `RISK_SCORE`.
