# CONCORDIA

**Different Teams. Same Truth.**

Concordia is a Snowflake-native reference implementation for Problem Statement 5:
Supply Chain Ontology and Governed Conversational Analytics.

It demonstrates how planning, procurement, logistics, and leadership can ask
business questions in natural language and receive answers calculated from the
same published metric contracts, with visible definitions, scope, lineage,
freshness, exclusions, and evidence.

## Truth contract

Concordia uses one fictional manufacturer, Meridian Motion, because no public
dataset exposes a complete Supplier → Part → Plant → Shipment → Order → Customer
chain with every required metric input.

- Every operational row is explicitly `SYNTHETIC_*`.
- Every canonical number is `DERIVED_FROM_SYNTHETIC`.
- `OBSERVED` is forbidden by contract tests.
- Simulation results are not industry benchmarks, customer outcomes, or evidence
  of real-world improvement.
- The simulator may test semantic correctness. It may not validate predictive
  performance or causal claims about real companies.

## Product promise

For the same scope, period, as-of time, entitlement, metric id, and metric
version:

1. every persona receives the same numerator, denominator, and value;
2. every value is reproducible from a deterministic SQL contract;
3. the language model cannot create or modify a metric formula;
4. missing identity, units, currency, time, or cost inputs are disclosed;
5. ambiguity is clarified rather than guessed.

## Product shape

Concordia is one business application with progressive disclosure:

- **Ask** — governed conversational analytics;
- **Operations** — focused exception and supply-flow exploration;
- **Definitions** — metric and ontology contracts;
- **Audit** — question, interpretation, query, answer, and decision history.

There is no separate engineering application. Technical evidence is available
through an in-context Evidence/Governance drawer—source records, exclusions,
lineage, freshness, and contract details—without forcing business users into
backend screens.

## Document set

Read in this order:

1. [`docs/00-charter.md`](docs/00-charter.md) — locked product decisions and claims.
2. [`docs/01-prd.md`](docs/01-prd.md) — users, requirements, stories, and acceptance.
3. [`docs/02-ux-design.md`](docs/02-ux-design.md) — information architecture and UI.
4. [`docs/03-technical-architecture.md`](docs/03-technical-architecture.md) — Snowflake design.
5. [`docs/04-ontology-metrics.md`](docs/04-ontology-metrics.md) — entities and formulas.
6. [`docs/05-simulation-contract.md`](docs/05-simulation-contract.md) — generated world and source mess.
7. [`docs/06-evaluation.md`](docs/06-evaluation.md) — deterministic and LLM evaluations.
8. [`docs/07-security-governance.md`](docs/07-security-governance.md) — roles and controls.
9. [`docs/08-brand-logo.md`](docs/08-brand-logo.md) — identity, visual system, and logo prompt.
10. [`docs/09-demo-submission.md`](docs/09-demo-submission.md) — judging coverage and demo.
11. [`docs/10-build-handoff.md`](docs/10-build-handoff.md) — authoritative prompt for a build chat.

## Locked scope

- One simulated manufacturer.
- Three plants, three distribution centres, suppliers, customers, parts, BOMs,
  lots, orders, receipts, production, shipments, returns, invoices, and costs.
- Separate simulated ERP, MES, WMS, TMS, CRM, and IoT dock-sensor records.
- Five canonical metric contracts:
  - inbound supplier OTD;
  - outbound customer OTD;
  - unit fill rate;
  - days inventory;
  - landed cost per accepted unit.
- GS1 EPCIS-inspired events and IOF-informed business concepts, without claims
  of standards certification or conformance.
- Snowflake SQL, a native semantic view, Cortex Analyst, AI_COMPLETE narration,
  masking policies, and Streamlit in Snowflake.

## Explicit non-goals

- Demand forecasting, optimization, predictive ML, or autonomous replenishment.
- Claims about real suppliers, customers, savings, service levels, or benchmarks.
- Live ERP/WMS/TMS connectors in the hackathon build.
- A complete ERP, MES, WMS, TMS, CRM, or planning suite.
- An LLM that writes unrestricted SQL or invents business definitions.
- A visually impressive graph that cannot be reconciled to records.

## Build, deploy and verify

Requires a `[hackathon]` entry in `~/.snowflake/connections.toml` (key-pair auth) and a Python
environment with `snowflake-connector-python`, `snowflake-snowpark-python`, `streamlit`, `tomlkit`
and NumPy 2.2.6 (the simulator refuses other versions so seeded draws stay reproducible).

```powershell
python scripts/generate_world.py              # seeded synthetic world -> data/generated/world
python scripts/deploy.py                      # every step in order, ending with the batch-2 load
python scripts/deploy.py reset upload load1 resolve eval publish   # reload a regenerated world
python scripts/verify.py golden grid hero security ask personas ontology  # -> data/generated/verification.json
python -m pytest tests -q
```

Batch 2 is loaded by `LAND.LOAD_EXTRACTS('.*_b2[.]jsonl[.]gz')`; the stream-gated task
`CORE.RESOLVE_TASK` (suspended by default, run with `EXECUTE TASK`) resolves and republishes, which
restates the affected answers.

| Layer | Objects |
|---|---|
| `LAND` | `RAW_RECORD` (append-only, hashed), stream, quarantine |
| `CORE` | resolved ontology, lot/IoT ledger, knowledge graph, metric SQL functions `COUNT_RESULT_M1/M2`, `FILL_RESULT_M3`, `M4_RESULT`/`M4_GRID`, `LANDED_RESULT_M5` |
| `APP` | published grid, persona-masked secure functions, `ASK` / `ASK_METRIC`, `SUPPLY_CHAIN_ONTOLOGY` semantic view and guarded Analyst runner, Streamlit app `APP.CONCORDIA` |
| `GOV` | metric contracts, entitlements, rejected aliases, evidence, query audit, pipeline runs |

The Streamlit app is owned by `CONCORDIA_APP_OWNER`, which can read the `APP` layer only. To run
the same app locally against the account: `streamlit run streamlit/app.py`.

Known limits of the hackathon build: the world and all source feeds are synthetic; personas are
selected in the app and enforced through Snowflake roles/policies rather than mapped to corporate
SSO users; IoT events are simulated dock telemetry, not a live device connector. The primary Ask
mode uses Cortex Analyst over `APP.SUPPLY_CHAIN_ONTOLOGY`; the evidence-envelope mode remains
available for deterministic single-metric drill-down.

## Branch

`feat/concordia-governed-supply-chain`

