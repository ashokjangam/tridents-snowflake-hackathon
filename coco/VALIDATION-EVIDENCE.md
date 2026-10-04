# Patient 360 validation evidence

Validated on 2026-10-04 against the deployed `PATIENT_360` Snowflake database and
the pinned MITRE Synthea sample.

## Reproducibility

- Application unit tests: 35 passed.
- C-CDA parser tests: 6 passed.
- Python compilation: passed.
- PowerShell load-runner syntax: passed.
- Pinned archive bootstrap rehearsal: passed.
- Bootstrap output: 108 documents and 96,806 narrative rows.

## Live analyst-role evidence

`tests/expanded_questions.sql` completed as `PATIENT_360_ANALYST` and retrieved:

- member and encounter rows;
- conditions and medication rows;
- two care plans;
- laboratory rows, including HbA1c 5.8;
- procedure and immunization rows;
- claims joined to encounters;
- payer coverage spans; and
- C-CDA evidence in Problems, Medications, Plan of Care, Results, and Procedures sections.

The minimized `CORE.PATIENT` projection exposed zero prohibited columns. The expected-check
suite returned `FAILED_GATE_COUNT = 0` and `ASSERT_ZERO_FAILED_GATES = 0`.

## Deployment

`PATIENT_360.CORE.PATIENT_360_APP` was redeployed with `--replace`, then app usage was
granted to `PATIENT_360_ANALYST` and `PATIENT_360_ADMIN`.

This artifact contains no credentials, connection secrets, or patient data beyond the
documented synthetic aggregate evidence.
