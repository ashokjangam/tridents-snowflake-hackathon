# Build handoff

Copy the prompt below into a new Cursor chat from branch
`feat/concordia-governed-supply-chain`.

---

## Authoritative build prompt

You are implementing Concordia — “Different Teams. Same Truth.” — a
Snowflake-native submission for Problem Statement 5: Supply Chain Ontology and
Governed Conversational Analytics.

Repository:

`C:\Users\C306242\Phoenix\sainathch45\snowcore-pdm`

Branch:

`feat/concordia-governed-supply-chain`

The complete, approved product and technical contract is under:

`concordia/README.md`

and:

`concordia/docs/00-charter.md` through `concordia/docs/09-demo-submission.md`.

Read all documents before planning or editing. Treat them as normative in this
priority order:

1. `00-charter.md`
2. `04-ontology-metrics.md`
3. `05-simulation-contract.md`
4. `06-evaluation.md`
5. `07-security-governance.md`
6. `03-technical-architecture.md`
7. `01-prd.md`
8. `02-ux-design.md`
9. `08-brand-logo.md`
10. `09-demo-submission.md`

If documents appear inconsistent, stop and identify the exact conflict. Do not
silently choose a convenient interpretation.

### Required outcome

Build a production-quality hackathon reference implementation and local preview
under `concordia/` without modifying SnowCore, Pneumora, or AxisGuard.

The implementation must include:

- deterministic, versioned, seeded manufacturer simulation;
- hidden golden truth available only to tests;
- six messy source projections: ERP, MES, WMS, TMS, CRM, IoT;
- append-only canonical event ledger;
- canonical entities and effective-dated relationships;
- deterministic identity/UOM/FX/timezone resolution and quarantine;
- knowledge-graph node/edge projection;
- five versioned metric contracts exactly as documented;
- governed answer-envelope procedure;
- semantic view/model and verified questions;
- bounded Cortex Analyst and AI_COMPLETE integration; do not claim optional
  Search or Agent features unless they are actually deployed and verified;
- one polished Streamlit app with progressive evidence/governance disclosure;
- local fixture preview that does not reimplement formulas;
- golden, edge, metamorphic, persona, adversarial, security, and provenance tests;
- rerunnable Snowflake SQL deployment;
- permanent synthetic-data disclosure.

### Mandatory implementation order

1. Run a preflight check and inspect target account capabilities without
   mutating account-wide settings.
2. Freeze `CONCORDIA_SIM_V1`, metric contracts, seed derivation, benchmark
   period, and golden fixtures.
3. Implement reference/golden metric functions and edge tests.
4. Implement the simulator state machine and invariants.
5. Render messy source projections.
6. Build landing, quarantine, canonical ledger, identity resolution, and
   metric contributions.
7. Prove product metrics equal golden fixtures and replay is idempotent.
8. Build semantic and conversational objects.
9. Build the Streamlit UI and exported local fixtures.
10. Run persona parity, prompt-injection, security, accessibility, and full
    build verification.
11. Deploy only after local review and explicit user approval.

### Non-negotiable controls

- Never emit `OBSERVED`.
- Never call synthetic performance real, measured, customer, or industry data.
- Do not train any model.
- Do not place metric formulas in Streamlit, prompts, or local DuckDB.
- Do not grant app roles access to simulation truth/evaluation gold.
- Do not silently resolve bare “OTD.”
- Do not guess identity, UOM, FX, timezone, duty, or cost.
- Do not let Cortex query raw tables or write data.
- Do not use a generated narrative as the numeric source.
- Do not claim row-level security until deployed viewer-context tests pass.
- Do not use `ACCOUNTADMIN` as application owner.
- Do not alter the account event table.
- Do not use Snowpark Container Services unless the approved design changes.
- Do not deploy or open a PR without explicit approval.

### Snowflake feature policy

Prefer native Snowflake capabilities where they directly satisfy a requirement:
stages, Streams, Tasks, Dynamic Tables, secure views, Semantic Views/models,
Cortex Analyst, Cortex Search, Cortex Agents, AI_COMPLETE, Streamlit warehouse
runtime, masking/row-access policies, tags, Data Metric Functions, Alerts,
lineage, query history, and Time Travel.

Every feature must:

- be verified against the target account;
- have a deterministic fallback if optional;
- be used for a requirement, not for marketing.

Do not add Snowflake ML or fine-tuning.

Native Semantic View support is mandatory for a submission-complete release.
If unavailable, retain the secure governed/local fallback for review, label it
degraded, and report that PS5 completion is blocked.

### Product/UI policy

One app only, with the seven documented navigation pages:

- Overview
- Operations
- Ask Concordia
- Why it changed
- As-of replay
- One graph
- Governance

Primary users are nontechnical supply-chain leaders. Technical details are
progressively disclosed in Evidence/Governance, not placed in a second app.

The dependency ribbon must be focused, grouped, and accessible. Do not use a
force-directed graph.

The visual style must follow `02-ux-design.md` and the brand brief. It must not
inherit the current SnowCore visual design mechanically.

### Verification standard

The implementation is not complete until:

- all golden fixtures match exactly;
- all invariants and metamorphic tests pass;
- same-scope, same-entitlement personas return identical exact metric fields
  and evidence hash; wording/evidence order may differ;
- all origins are compliant;
- all unsupported prompts abstain or clarify;
- generated SQL is allowlisted;
- narrative numeric faithfulness passes;
- local preview is clearly labelled and matches deployed fixtures;
- local preview refuses arbitrary new questions and contains no calculation
  implementation;
- recently edited files have no introduced lints;
- the repository contains no secrets.

### Working style

Use appropriate planning, implementation, test, review, security, and build
verification subagents. Keep one authoritative task list. Preserve the user's
untracked work. Make focused commits on the existing Concordia branch after
verification. Report verified facts separately from assumptions.

Before implementation, return:

1. capability/preflight findings;
2. exact file plan;
3. any contradictions or decisions genuinely requiring user approval;
4. what the proposed build will not achieve.

Stop and report every contract inconsistency. Wait for approval if resolving it
would change a normative contract; otherwise proceed.

---

## Expected initial repository structure

```text
concordia/
  README.md
  docs/
  src/concordia/
  sim/
  eval/
  data/
    fixtures/
    generated/
  sql/
    00_setup.sql
    01_contracts.sql
    01_gov.sql
    02_land.sql
    03_core.sql
    04_metrics.sql
    05_app.sql
    06_semantic.sql
    07_streamlit.sql
    08_eval.sql
    09_personas.sql
  streamlit/
    app.py
    environment.yml
  tests/
```

Generated bulk data should be ignored unless a small fixture is intentionally
versioned.

