# Patient 360 validation evidence

Validated on 2026-10-04 against the deployed `PATIENT_360` Snowflake database and
the pinned MITRE Synthea sample.

## Reproducibility

- Application unit tests: 40 passed.
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

`tests/allergy_cohort.sql` validated all 108 members: 87 have zero allergy rows, 5 have
one row, and 16 have multiple rows (maximum 10). No allergy row is missing a citation key,
and 210 allergy document rows carry rejected-code evidence for the live guard.

The frozen risk audit remains 97 members and 14 events. The app now displays bucket
population, event count, and observed event rate together and explicitly identifies the
non-monotonic and sparse buckets.

## Deployment

`PATIENT_360.CORE.PATIENT_360_APP` was recreated and deployed under the scoped
`PATIENT_360_ADMIN` role because this account does not support Streamlit ownership transfer.
The app owner is now `PATIENT_360_ADMIN`; app usage is granted to both analyst and admin roles.
Users `ASHOK`, `SAINATH`, and `SIDHARTH` each hold the scoped admin role and no teammate was
granted `ACCOUNTADMIN`. The deployer role does not inherit the loader role and cannot enter RAW.

This artifact contains no credentials, connection secrets, or patient data beyond the
documented synthetic aggregate evidence.
