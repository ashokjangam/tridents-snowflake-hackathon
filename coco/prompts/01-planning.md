# Planning prompt

Paste this before the first `COPY` into `PATIENT_360`. Do not create objects in this turn. Do not invent rows, member ids, notes, or risk rates.

You are recording the Patient 360 plan for a Streamlit-in-Snowflake demo. Read `patient-360/README.md`, `TRACK-DECISION.md` section 3, and `research/patient-360.md`. Do not edit those research files.

Write a short plan that includes only the following:

1. Database `PATIENT_360`, warehouse size XS. One Streamlit page. No second app.
2. `RAW`: the 18 CSV tables already extracted under `data/csv/`, plus `DOCUMENT_SECTION` parsed from `data/ccda/` (`document_id`, `patient_id`, `section_loinc`, `section_title`, `element_id`, `text`, `code`). `document_id` equals `patient_id`.
3. `CORE` views named in `patient-360/README.md`. They omit `SSN`, `DRIVERS`, and `PASSPORT`. `RISK_SCORE` uses CSV facts before 2023-01-01 and does not include C-CDA text. The four points stay as already measured. Do not retune them.
4. The page queries those `CORE` views with bound SQL. It does not query a maintenance semantic view (`PNEUMORA`, `SNOWCORE_REAL`, `TRIDENT_OPS`).
5. Frozen questions and refusals listed in `patient-360/README.md`. An answer without a citation tuple is a refusal. `AI_COMPLETE` is optional, temperature 0, and limited to rows the SQL step returned.
6. Bans: no synthetic note, no filled member id, no openFDA load, no trained model, no sentence that calls the point count a validated model or a care recommendation.

End with the object list and the bans. Do not run `COPY`. Do not print secrets.
