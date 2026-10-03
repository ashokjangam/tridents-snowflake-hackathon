# Security, governance, and operations

## Security objectives

- Prevent product access to hidden simulation truth.
- Prevent LLM access to raw/unapproved sources.
- Enforce row and cost visibility independently of UI filters.
- Preserve immutable evidence and audit history.
- Keep deployment isolated from SnowCore, Pneumora, and AxisGuard.
- Avoid account-wide changes unless explicitly approved.

## Roles

### `CONCORDIA_ADMIN`

Owns database-level administration and deployment. Not an application runtime
role.

### `CONCORDIA_INGEST`

Writes staged/landing data and manifests. Cannot publish metrics.

### `CONCORDIA_TRANSFORM`

Builds canonical/event/metric projections. Cannot read hidden truth or
evaluation defect labels. Evaluation runs under `CONCORDIA_TEST` in a separate
task/session after product outputs are materialized.

### `CONCORDIA_APP_OWNER`

Owns the Streamlit object and approved app procedures. Reads only secure app
objects and required governed metadata; cannot read simulation truth, landing,
raw core, quarantine, or evaluation objects.

### `CONCORDIA_APP`

Reads secure app objects and calls approved procedures. Cannot query raw,
quarantine, or evaluation truth.

### `CONCORDIA_AUDITOR`

Reads contracts, evidence, lineage, quality, and audit logs. Sensitive costs
remain governed.

### `CONCORDIA_TEST`

Reads hidden truth and golden fixtures. Never owns or runs Streamlit.

### Persona roles

`CONCORDIA_PLANNER`, `CONCORDIA_PROCUREMENT`, `CONCORDIA_LOGISTICS`, and
`CONCORDIA_EXECUTIVE` query the same semantic view. Procurement and Executive
inherit `CONCORDIA_COST_READER`; Planning and Logistics do not.

## Persona entitlements

`GOV.ENTITLEMENT` stores the app persona, effective dates, cost visibility,
audit visibility and `ALLOWED_FACILITIES`. Logistics (Elena Voss, Logistics
Manager, Americas) is limited to Dayton, Reno, Newark and Oakland; every other
persona has `["*"]`.

Persona names do not grant object privileges. Real Snowflake persona roles
prove the semantic layer independently, while the Streamlit dropdown records
the selected persona for the conditional cost masking policy.

## Row and column controls

- Row access policy `GOV.SITE_ACCESS` on the semantic-view tables (`SV_RESULT`,
  `SV_LINE_OUTCOME`, purchase and sales order lines, receipts, cost documents,
  lots, promises, shipments, IoT and consumption) hides rows whose site is not
  in the persona's `ALLOWED_FACILITIES`. A persona role is matched by name
  (`CONCORDIA_LOGISTICS` → `LOGISTICS`); the app owner is matched through the
  persona recorded for its session in `GOV.APP_PERSONA_CONTEXT`.
- Rows with no site (network, part, region, supplier and customer answers) stay
  visible to every persona. They are aggregates that include other sites, so the
  restriction is on site-level answers and site records, not on totals.
- `APP.RESULTS_FOR`, `BREAKDOWN_FOR`, `CONTRIBUTION_FOR`, `RECEIPTS_FOR` and
  `ASK_METRIC` apply the same rule and return `FORBIDDEN` with
  `SITE_NOT_ENTITLED`.
- Conditional masking policies protect landed-cost result columns and cost
  document amounts. A persona without cost access reads the landed-cost status
  as `WITHHELD`, not `COMPLETE`, so a blank never passes for a finished answer.
- `scripts/verify.py personas` logs in as each persona role, checks that
  Logistics reads no other-site rows while the others do, checks that answers
  every role may see are identical, and stores the per-role result in
  `GOV.PERSONA_CHECK` (shown on the Governance page).
- Secure views expose only governed fields.
- UI filters are convenience, not security.

Warehouse-runtime Streamlit identity behavior must be release-tested. If the
runtime resolves every viewer as the owner, the product must not claim
production-grade per-user row enforcement until an approved architecture
supports it.

## LLM boundary

Allowed:

- Cortex Analyst over approved semantic view;
- deterministic `ASK_METRIC`;
- AI_COMPLETE over stored answer envelope.

Forbidden:

- raw source tables;
- hidden truth/evaluation labels;
- arbitrary procedure execution;
- inserts/updates/deletes;
- dynamic formula generation;
- prompt-controlled object names;
- unrestricted SQL execution.

Generated SQL is parsed/checked against an object and operation allowlist before
execution.

## Evidence and audit

For each question store:

- user/persona;
- original and normalized question;
- clarification choices;
- scope/defaults;
- metric/version;
- semantic object;
- generated or verified SQL hash;
- Snowflake query id;
- result/evidence hash;
- model/tool version;
- answer status;
- timestamp.

Evidence records are append-only. Corrections create a new evidence version.

## Data governance

Every canonical field has:

- business definition;
- owner;
- source mapping;
- valid UOM/domain;
- sensitivity;
- quality rule;
- lineage;
- effective dates.

Every metric has:

- owner/approver;
- semantic version;
- hash;
- grain;
- clock;
- inclusion/exclusion policy;
- test suite;
- published state.

Metric changes require contract/version/test changes in the same commit.

## Operational observability

Deployed:

- query tags;
- task history;
- pipeline run log;
- source/metric freshness watermarks;
- quarantine counts;
- quality checks;

Data Metric Functions, automated object-lineage snapshots, Dynamic Tables and
Snowflake Alerts are not deployed.

Do not overwrite the account event-table setting already used by another
project.

## Recovery

- Time Travel protects tables operationally.
- Re-running an ingest manifest is idempotent.
- Graph/current-state projections can rebuild from ledger.
- Golden seed/version reproduces the simulated world.
- Normal deployment never drops/recreates append-only ledger/evidence tables.
- Reset procedures are explicit, test-only, and require elevated role.

## Privacy and sensitive data

The simulation contains no real personal or customer data.

Still apply enterprise patterns:

- synthetic names clearly fictional;
- avoid real addresses/contact details;
- role-based cost masking;
- no secrets/tokens in data or code;
- no external calls in the application;
- generated exports carry origin and sensitivity labels.

## Threats and controls

Prompt injection:

- semantic allowlist;
- system instructions not to follow data-row instructions;
- no write tools;
- adversarial benchmark.

Metric spoofing:

- formula hash;
- one published object;
- contribution-grain tests;
- no UI formula.

Evidence leakage:

- evidence retrieval enforces same entitlement;
- opaque evidence ids;
- secure views.

Gold leakage:

- no product grants;
- static schema checks;
- query-history tests.

Late/stale data:

- as-of semantics;
- visible freshness;
- stale status;
- no “live” claim.

Synthetic misrepresentation:

- permanent watermark;
- origin field in every answer/export;
- forbidden-claim tests.

## Release gates

- least-privilege grants reviewed;
- hidden truth inaccessible to app;
- landed-cost masking tested as each Snowflake persona role and through the app
  owner with selected persona context;
- Cortex SQL allowlist tested;
- prompt-injection suite passes;
- evidence access cannot bypass scope;
- no secrets in repository;
- no account-wide mutation without explicit approval;
- all objects under `CONCORDIA`;
- all generated data labelled synthetic.

