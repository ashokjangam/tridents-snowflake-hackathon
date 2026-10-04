# CoCo evidence checklist

Capture these artifacts before rehearsal. A checkbox is done only when the artifact exists and a person has looked at it. Do not invent a query id, a row count, or a screenshot.

Store logs and query ids next to this file or in the hackathon evidence folder the team already uses. Do not store passwords, tokens, or key files.

The page under `streamlit/` and the tests under `app/tests/` are the application evidence. Warehouse objects are evidence only after they are created in the account.

## Planning (before the first `COPY`)

- [ ] Track decision and the six frozen questions are named, including the two extra refusals (external claims, treatment advice).
- [ ] Object list is written: `RAW` tables, `RAW.DOCUMENT_SECTION`, `CORE` views in `README.md`, one Streamlit page. `SEM_MEMBER` is optional and is not on the page's query path.
- [ ] Written bans are attached: no synthetic note, no retuned points, no openFDA load, no maintenance semantic view, no claim that the point count is a validated model, no `SSN` / `DRIVERS` / `PASSPORT` on the analyst role.
- [ ] Prompt used: `coco/prompts/01-planning.md`. Save the CoCo session log.

## Development (as the page and views are written)

- [ ] `app/queries.py` matches the views that were created, or the difference is written down before the demo.
- [ ] Citation contract is the one in `app/citations.py`: document tuple, table tuple, and cohort tuple for `RISK_SCORE` only.
- [ ] Allergy answers quote the allergy-row code. A second code can appear only with the "not quoted" wording.
- [ ] `AI_COMPLETE` is off by default, temperature 0, and discarded when `accept_narration` fails.
- [ ] Prompt used: `coco/prompts/02-development.md`. Save the session log and the file list it reviewed.

## Execution (when the account changes)

- [ ] Database `PATIENT_360` and an XS warehouse exist. The log names the warehouse.
- [ ] Load commands and the Streamlit deploy command are in the log, with query ids for the row-count checks and for question 1.
- [ ] The log does not point this demo at `PNEUMORA`, `SNOWCORE_REAL`, or `TRIDENT_OPS`.
- [ ] The stage contains `patient_360.py`, `environment.yml`, and `app/`.
- [ ] Prompt used: `coco/prompts/03-execution.md`. Save the Snowflake CLI transcript and the query ids.

## Testing (before rehearsal)

- [ ] `python -m unittest discover -s app/tests -t . -v` from `patient-360` passes. Save the text output.
- [ ] A worksheet or CLI transcript matches the expected-check table in `README.md`, including orphan counts of 0 and the 108/108 document match.
- [ ] Screenshots show questions 1, 2, and 3 with the tuples visible, and questions 4 and 5 with the refusal text. Question 6 (openFDA) and the treatment question are refused on screen.
- [ ] If a live count disagrees with the README table, the disagreement is written here and rehearsal uses the queried number only after the load is fixed. A drifted count is not explained away.
- [ ] Narration checkbox is shown off. If someone turns it on, the saved shot still shows the deterministic answer, and any discarded narration is not presented as the answer.
- [ ] Prompt used: `coco/prompts/04-testing.md`. Save the test output and the screenshot file names.

## Failed check

| Check | Live result | Inspection figure | Stopped? |
| --- | --- | --- | --- |
| | | | |
