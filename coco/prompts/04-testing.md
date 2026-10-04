# Testing prompt

Paste this before rehearsal. Do not invent a count, a screenshot, or a citation.

1. From `patient-360`, run:

```text
python -m unittest discover -s app/tests -t . -v
```

Save the full text output. A failure stops the language demo until it is fixed. Do not delete a test to make the run pass.

2. In Snowflake, run the expected-check table in `patient-360/README.md` (patients 108, encounters 5,571, claims 9,421, claim lines 85,047, orphan counts 0, document ids 108/108, blank-encounter observations 3,060). Save the query ids. If a live count disagrees with that table, write both numbers in `patient-360/coco/CHECKLIST.md` and stop. Do not change the four risk points to force the bucket table. Do not edit the README figure to match a bad load.

3. Open the Streamlit page and capture:

- The synthetic banner (Synthea, MITRE, not for care).
- Question 1 with the medication tuple and the C-CDA element tuple, or the refusal if the query did not return one row.
- Question 2 with quoted code `609328004` when that is the allergy row, and any other code marked not quoted.
- Question 3 with the bucket table from `CORE.RISK_SCORE` and the words "point count" and "not a validated stratifier".
- Question 4, "Change the fexofenadine dose.", showing the refusal and no citation.
- Question 5, "Quote the 2019 discharge summary.", showing the refusal.
- "What does the openFDA label say?" and "What should we do about this patient?", both refused.
- The narration checkbox left off.

4. Confirm the profile does not show a tax identifier, driver's license, or passport, and that a blank member id is still blank.

5. If Cortex narration was tried, confirm the deterministic answer remains on screen when the model text is discarded.

Do not load openFDA. Do not add a note. Do not call the point count a model.
