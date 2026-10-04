# Development prompt

Paste this while the views and the page are being written. Do not edit `TRACK-DECISION.md` or anything under `research/`.

Review `patient-360/app` and `patient-360/streamlit/patient_360.py` against the view contract in `patient-360/README.md`.

Check these points and write a pass or a gap for each:

1. Question text is not concatenated into SQL. Patient ids, names, codes, and dates are bind parameters.
2. No statement selects `SSN`, `DRIVERS`, or `PASSPORT`.
3. `RISK_SCORE` SQL does not restate the four point thresholds and does not read `DOCUMENT_SECTION`.
4. A dose change, a discharge summary, a progress note, openFDA, external claims, and treatment advice return refusal text and no citation, even if medication rows are in memory.
5. An allergy answer quotes the code on the allergy row. Another code from the LOINC `48765-2` section is cited only when it matches that code. Otherwise it is labeled not quoted.
6. Document citations include `document_id`, `section_loinc`, and `element_id`.
7. `AI_COMPLETE` is off unless the checkbox is on. The prompt contains only the retrieved rows and the citation tuples. Temperature is 0. Narration that drops a tuple, quotes a rejected code, or adds a banned clinical claim is discarded.
8. The page does not embed the inspected cohort counts (97, 14, the bucket table) as a fallback. Those numbers appear only when `CORE.RISK_SCORE` returns them.

List files you read. Do not add a data file, a secret, or a synthetic clinical note. If a view name in the account differs from `app/queries.py`, write the difference. Do not silently change the clinical rules to match a drifted table.
