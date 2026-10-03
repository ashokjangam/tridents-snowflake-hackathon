# Technical architecture

## Architectural principles

1. Metric SQL is the only numeric authority.
2. LLMs interpret and explain; they do not calculate.
3. Raw systems remain distinct; ontology resolves them.
4. Event history is append-only.
5. Business valid time and warehouse recorded time are separate.
6. Missing data reduces coverage or causes abstention; it is never silently
   zero-filled.
7. Identity matches are deterministic in v1.
8. Every path is reproducible by contract version and seed.
9. Local preview displays exported governed envelopes; it does not reimplement
   formulas.
10. All objects are isolated in database `CONCORDIA`.

## Logical architecture

```text
Simulator truth (test-only)
        |
        +--> ERP JSON/CSV  --+
        +--> MES JSON/CSV  --|
        +--> WMS JSON/CSV  --+--> LAND --> CORE EVENT LEDGER
        +--> TMS JSON/CSV  --|               |
        +--> CRM JSON/CSV  --|
        +--> IoT JSON/CSV  --+               +--> canonical entities
                                                +--> identity/UOM/FX resolution
                                                +--> knowledge-graph projection
                                                +--> metric contribution grains
                                                         |
                                                         v
                                                GOVERNED METRIC VIEWS
                                                         |
                          +------------------------------+------------------+
                          |                              |                  |
              SUPPLY_CHAIN_ONTOLOGY              ASK_METRIC         Evidence store
                          |                              |                  |
                    Cortex Analyst                    AI_COMPLETE narration
                          +------------------------------+------------------+
                                                         |
                                                  Streamlit app
```

The app and product roles cannot read simulation truth or golden evaluation
labels.

## Snowflake object model

Database: `CONCORDIA`

### `SIM`

Test-only world, seed, event generation, source projections, scenario catalog,
and hidden causal labels.

### `LAND`

Internal stages, manifests, raw `VARIANT` payloads, checksums, source files, and
quarantine.

### `CORE`

Canonical entities, bitemporal master data, event ledger, identity maps,
resolution candidates, current-state projections, knowledge-graph nodes/edges,
and metric-contribution grains.

### `GOV`

Metric contracts, formula hashes, ontology definitions, source mappings, UOM,
FX, entitlements, verified questions, evidence envelopes, query audit, pipeline
runs, quality results, model pins, and alerts.

### `APP`

Secure views, the native `APP.SUPPLY_CHAIN_ONTOLOGY` semantic view, guarded
stored procedures, and the Streamlit object. Cortex Search and Cortex Agents
are not deployed in this build.

## Ingestion

Each raw row contains:

- source system;
- source record id;
- source revision;
- recorded timestamp;
- extracted timestamp;
- visible timestamp;
- payload hash;
- origin;
- generator version;
- seed stream;
- scenario id.

Idempotency key:

`(source_system, source_record_id, source_revision, payload_hash)`

The same row replay is a no-op. A changed revision appends a new record.

`GOV.SOURCE_MAPPING` is the onboarding contract. Each versioned row maps source
system/object/field to canonical entity, attribute or event field; records
transform rule, datatype, UOM/timezone/currency policy, required/optional
status, owner, effective dates, and validation rule. No production mapping may
exist only in parser code.

Pipeline:

1. simulator writes versioned files and manifest to an internal stage;
2. `COPY INTO` lands raw `VARIANT`;
3. standard table stream captures new rows;
4. task graph parses and validates source-specific records;
5. invalid records enter quarantine with reason codes;
6. deterministic aliases, units, currency, and timezone are resolved;
7. EPCIS-inspired events append to the canonical ledger;
8. current state and metric grains refresh;
9. run, quality, and freshness records are committed.

## Temporal model

Snowflake Time Travel is recovery, not bitemporal business logic.

Master/event records include:

- `VALID_FROM`, `VALID_TO` — when the fact applies in the simulated world;
- `RECORDED_FROM`, `RECORDED_TO` — when Concordia knew that version;
- `EVENT_TIME` — when the operational event occurred;
- `RECORD_TIME` — when the source committed it;
- `VISIBLE_AT` — when it became usable by Concordia.

Every metric accepts `RECORDED_AS_OF`. A row is visible only when
`VISIBLE_AT <= RECORDED_AS_OF` and no visible revision supersedes it.

## Event ledger

Use GS1 EPCIS 2.0 concepts without claiming certification:

- ObjectEvent;
- AggregationEvent;
- TransactionEvent;
- TransformationEvent.

Required fields:

- event id/type;
- event and record times;
- timezone;
- action;
- business step;
- disposition;
- read point/location;
- source/destination party;
- product/lot/serial;
- quantity and base UOM;
- linked business transactions;
- correction/error declaration;
- original payload.

Corrections append new events. They do not mutate history.

## Entity resolution

Automatic linkage is allowed only through:

- administered source aliases;
- GTIN-like product identifiers;
- GLN-like location identifiers;
- serial/lot plus owning organization;
- exact deterministic business keys.

Fuzzy similarity may create a candidate but may not publish a `same_as` edge.
Unresolved rows are excluded and counted. The UI can display candidates to a
steward but v1 has no write-enabled MDM workflow.

## Metric computation

Each metric has:

- contract table row;
- semantic version;
- definition hash;
- contribution-grain table/view;
- published aggregate view;
- verified queries;
- golden tests.

Analyst-facing metric inputs contain numerator and denominator contributions,
not raw timestamps from which another OTD can be invented.

No formula may exist in Streamlit, prompts, or local DuckDB.

`APP.ASK_METRIC` accepts:

- metric id;
- optional version;
- scope JSON string;
- valid period;
- recorded-as-of.

It returns an answer envelope and writes an immutable evidence record.

Change explanations come from a deterministic metric bridge, not generated
prose. For two compared envelopes, `APP.METRIC_BRIDGE` groups exact contribution
changes into governed buckets (population entered/exited, on-time-to-late,
late-to-on-time, quantity, scope, exclusion, and late-record visibility). Bucket
deltas must reconcile exactly to numerator and denominator deltas. Operational
conditions such as a quality hold may be cited only when a visible event path
links the changed contribution to that condition.

## Answer envelope

Required fields:

- evidence id;
- metric id/version/hash;
- plain definition;
- value/unit/status;
- numerator/denominator;
- grain;
- valid period;
- recorded-as-of;
- applied scope/defaults;
- excluded count;
- coverage;
- freshness/SLA;
- source systems/origins;
- governed object/query id;
- technical lineage reference;
- caveats.
- deterministic driver buckets and reconciliation hash for change questions.

Streamlit renders this envelope before optional narrative generation.

## Cortex use

### Cortex Analyst

Use for natural-language-to-SQL against the approved semantic view. Include
verified queries and explicit instructions separating supplier and customer
OTD.

The application resolves aliases and clarification requirements before an
Analyst call. Bare OTD, fill rate, inventory, cost, missing scope, and unsupported
requests cannot reach Analyst until resolved.

The deployed semantic view publishes governed result rows, parts, sites,
regions, suppliers, customers, metric contracts, supply links, BOM links,
production capabilities, recursive sourcing, substitutions, production
consumption, end-to-end supplier-to-customer traces, IoT/lot events, the stored
per-line outcomes behind each OTD and fill-rate answer (`line_outcomes`), and
operational records: purchase order lines, receipts, cost documents, received
lots, sales order lines, promises, shipments and lot allocations. Each table
reaches parts, sites and parties through exactly one join path, because
Snowflake rejects queries over a multi-path relationship.

Each governed metric is `IFF(COUNT(key) = 1, MAX(value), NULL)`: it returns the
published value only when exactly one published answer matches, so an
unfiltered or under-filtered query returns null rather than an arbitrary row.

The 23 verified questions are one catalog. Each `vq_NN` entry on the semantic
view has the same id and text as `GOV.VERIFIED_QUESTION` row `VQ-NN`; deploy
fails if they differ, mirrors the SQL into `ANALYST_SQL`, and the app reads both
through `APP.ANALYST_VERIFIED`.

Only approved joins are allowed: result-to-dimensions through governed scope
keys, contribution-to-result through evidence id, and relationship endpoints
through canonical entity ids. Synonyms/rejected aliases come from the ontology
contract. Verified queries must cover every benchmark class. Analyst may select,
filter, group, and compare published results; it may not recalculate a ratio,
average percentages, infer a completion clock, or query raw event timestamps.
`scripts/verify.py ontology` executes the primary multi-metric, end-to-end trace,
and IoT/lot verified queries through the guarded semantic path. `personas`
compares the same OTD question for planning, procurement, and logistics.

### Cortex Search

Not deployed. Definitions and ontology terms are queried from governed tables.
Search remains a possible extension and is not used as numeric evidence.

### AI_COMPLETE

Use only to narrate a stored answer envelope. Pin the model. Suppress prose if it
introduces any numeric token absent from the envelope or violates required
caveat/origin fields.

### Cortex Agent

Not deployed. The Streamlit app routes directly to Cortex Analyst for the
primary semantic answer and to `ASK_METRIC` for deterministic evidence drill-down.

### Snowflake ML

Do not use it in v1. PS5 does not require prediction, and training against the
simulation would not establish real-world model performance.

## Native Snowflake features

Deployed:

- internal stages and file formats;
- Streams and Tasks;
- standard tables and secure views;
- native Semantic View for the submission path;
- Cortex Analyst and AI_COMPLETE;
- Streamlit in Snowflake on warehouse runtime;
- conditional masking policy for landed cost;
- row access policy for site entitlement;
- query tags and account usage history;
- Time Travel for operational recovery.

Not deployed: Dynamic Tables, Cortex Search, Cortex Agents, Data Metric
Functions, Alerts, and automated `GET_LINEAGE` snapshots.

Do not use merely for marketing:

- Snowpark Container Services;
- external model endpoints;
- ML training/fine-tuning;
- hybrid tables;
- Iceberg;
- Document AI;
- unrestricted generated SQL;
- a third-party graph database.

Feature availability must be tested on the target account. Every optional
feature needs a deterministic fallback.

Native Semantic View support is a PS5 completion requirement, not optional
decoration. A secure governed-view/local-fixture fallback keeps the demo usable
but must be disclosed as degraded mode and cannot satisfy the semantic-view
release gate.

## Knowledge graph

Snowflake has no native openCypher graph engine in this design.

Represent:

- `CORE.KG_NODE`
- `CORE.KG_EDGE`

Edges include type, valid/recorded intervals, source/evidence id, origin, and
resolution method.

Traverse with bounded recursive CTEs. Depth is capped. The graph is a projection
of the event/entity ledger and can be rebuilt.

## Security

Roles:

- `CONCORDIA_ADMIN`
- `CONCORDIA_INGEST`
- `CONCORDIA_TRANSFORM`
- `CONCORDIA_APP`
- `CONCORDIA_APP_OWNER`
- `CONCORDIA_AUDITOR`
- `CONCORDIA_TEST`

Product persona entitlements are data, not separate metric views.

`CONCORDIA_APP_OWNER` owns Streamlit and approved app procedures, can read only
secure `APP`/required `GOV` objects, and cannot read `SIM`, `LAND`, raw `CORE`,
or evaluation objects. `CONCORDIA_ADMIN` does not own or run the app.

Controls:

- product roles have no `SIM`/gold access;
- procedures execute with minimum required rights;
- costs use masking policy;
- site entitlement uses `GOV.SITE_ACCESS` (row access policy) and the persona
  functions; aggregates with no site stay visible to every persona;
- no `ACCOUNTADMIN` app ownership;
- no writes from Cortex tools;
- app SQL is allowlisted to approved procedures/views.

Warehouse-runtime Streamlit viewer identity must be tested. If viewer context
cannot safely support row policies, the implementation must not claim
production-grade persona security.

## Performance and cost

Start with:

- one XS transform warehouse;
- one XS app/Cortex warehouse;
- auto-suspend;
- finite simulation scale;
- precomputed contribution grains;
- bounded trace depth;
- no LLM calls on ingestion/refresh.

Clustering, larger warehouses, and high-frequency ingestion require measured
query evidence before adoption.

## Reliability

Expected failure behavior:

- duplicate row → no-op;
- invalid UOM/timezone → quarantine;
- unresolved identity → exclusion/abstention;
- missing cost component → incomplete coverage;
- late event → later as-of restatement;
- refresh failure → return last good answer marked stale;
- generated SQL outside allowlist → refusal;
- narrative adds unsupported number → suppress narrative;
- task replay → idempotent result;
- graph disagreement → rebuild graph from ledger.

## Local preview

Local preview reads exported governed fixture envelopes and trace records.

It may:

- render every page and state;
- demonstrate benchmark questions;
- show exact frozen evidence.

It may not:

- recompute metrics in Python/DuckDB;
- claim live Cortex behavior;
- answer arbitrary new questions.

The UI must label fixture mode.

## Deployment sequence

1. roles, warehouses, database, schemas, stages;
2. contracts and ontology;
3. simulator and projected files;
4. landing/parse/quarantine;
5. canonical ledger/entity resolution;
6. metric grains and views;
7. security policies;
8. semantic view and verified queries;
9. guarded Analyst and deterministic metric procedures;
10. Streamlit;
11. fixture/evaluation run;
12. release gates.

All scripts must be rerunnable. Destructive reset is a separate explicit test
procedure and never part of normal deployment.

