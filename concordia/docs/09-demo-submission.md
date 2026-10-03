# Demo and submission strategy

## One-sentence pitch

Concordia gives planning, procurement, and logistics one governed answer by
binding natural-language questions to versioned supply-chain entities,
relationships, and metric contracts.

## Thirty-second setup

Meridian Motion's ERP says an order shipped. TMS says delivery failed. WMS says
inventory exists, but some is on quality hold. CRM revised the promise.
Procurement and logistics can each defend a different OTD number.

Concordia does not ask an LLM to choose the winner. It publishes the business
definition once, resolves each source into that contract, and shows the evidence
behind the result.

## Five-minute demo

### 0:00–0:35 — The disagreement

Show three role quotes with different interpretations of OTD.

State immediately:

> Meridian Motion is a simulated manufacturer. The integration and metric
> behavior are evaluated deterministically; no result is presented as observed
> customer performance.

### 0:35–1:20 — One governed answer

Nora asks:

> Why did outbound customer OTD for MM-440 change in May 2026?

Show:

- metric id/version;
- numerator/denominator/value;
- product/period/as-of scope;
- freshness and coverage;
- direct explanation.

### 1:20–2:10 — Trace the business path

Open the dependency ribbon:

Supplier → revised bearing → Dayton plant → shipment attempts → order lines →
Northeast customers.

Differentiate:

- proven event links;
- contributing conditions;
- unresolved records;
- customer ratings that are associated but not metric inputs.

### 2:10–2:50 — Same truth across teams

Switch through planning, procurement, and logistics users with one temporary
equal-entitlement benchmark cohort.

Show that the explanation ordering changes, but metric id/version, scope,
numerator, denominator, value, exclusions, and evidence hash do not.

### 2:50–3:35 — Time and cost truth

Switch to a cost-entitled procurement user. Rewind to the earlier
recorded-as-of. A late freight/brokerage invoice is absent,
so landed cost is incomplete. Move forward; landed cost restates. Customer OTD
does not change unless delivery evidence changed.

### 3:35–4:15 — Governance, not chatbot theatre

Ask:

> What is OTD?

Concordia asks whether the user means supplier or customer OTD.

Ask:

> Treat missing duty as zero.

Concordia refuses and identifies incomplete coverage.

### 4:15–5:00 — Technical proof

Open Evidence/Governance:

- formula/version/hash;
- numerator/denominator;
- excluded rows;
- source origins;
- query/evidence id;
- verified persona-parity/golden tests.

Close:

> Different teams can ask naturally. Concordia resolves the answer through the
> same governed truth.

## PS5 requirement traceability

1. **Ontology — entities, relationships, hierarchies, canonical metrics**
   - Normative contract: `04-ontology-metrics.md`.
   - Build artifacts: governed entity/relationship/alias/metric tables and
     knowledge-graph projection.
   - Proof: ontology catalog, edge evidence, five exact golden metric fixtures.
2. **Semantic views encode business meaning**
   - Logical tables, allowed joins, dimensions, synonyms, rejected aliases, and
     verified-query rules: `03-technical-architecture.md`.
   - Build artifact: native Semantic View in `sql/06_semantic.sql`. A secure
     governed fallback is degraded demo mode and does not pass this requirement.
   - Proof: guarded semantic execution of the primary multi-metric,
     end-to-end trace, and IoT/lot questions; exact metric-grid parity is
     checked separately by `scripts/verify.py grid`.
3. **Governed conversational analytics**
   - Intent, clarification, refusal, evidence envelope, and LLM boundary:
     `01-prd.md`, `03-technical-architecture.md`, and
     `07-security-governance.md`.
   - Proof: NL benchmark, SQL allowlist, numeric-faithfulness, and provenance
     tests.
4. **One metric resolves identically across personas**
   - Contract: same scope, period, as-of, version, and equal entitlement.
   - Demo users: planning, procurement, and logistics.
   - Proof: `scripts/verify.py personas` sends the same OTD question as
     planning, procurement, and logistics and compares metric id, status,
     numerator, denominator, display and scope; it also compares semantic-grid
     fingerprints as the real Snowflake persona roles.

## Judging coverage

These are build acceptance targets, not claims that the documentation itself
implements them.

### Real-world relevance

- realistic ERP/MES/WMS/TMS/CRM boundaries;
- source identity/UOM/currency/timezone conflicts;
- partial fulfillment, quality holds, promise revisions, late invoices,
  failed delivery, returns, ratings, and locality;
- standards-informed ontology/event concepts without a conformance claim;
- enterprise onboarding/mapping pattern;
- permanent simulation disclosure.

What it does not prove: adoption or outcomes at a real manufacturer.

### Technical execution

- append-only event ledger;
- bitemporal knowledge;
- deterministic entity resolution;
- versioned metric contracts;
- semantic views;
- constrained Cortex use;
- evidence envelopes;
- late-data replay;
- cost masking and site row-access policies, proven by logging in as each
  persona role (in the app the persona is picked from a list, so the app
  demonstrates the rule rather than enforcing it per login);
- golden/metamorphic/persona/adversarial tests;
- local preview and native deployment.

### Solution completeness

- all required entities/relationships;
- all required metrics;
- governed natural language;
- same-metric persona proof;
- definitions/evidence/audit;
- ambiguity/refusal;
- polished role-appropriate UI.

## Submission assets

- repository and reproducible setup;
- deployed Streamlit URL;
- local preview instructions;
- architecture diagram;
- ontology diagram;
- metric-contract summary;
- truth/model card;
- test/evaluation summary;
- 5-minute video;
- concise deck;
- data-origin disclosure;
- logo assets.

Capture checklist:

- landing/Ask with permanent simulation disclosure;
- ambiguous OTD clarification;
- governed answer with metric/version/scope/as-of;
- deterministic Why bridge and reconciliation;
- dependency ribbon plus accessible list;
- Evidence/Governance drawer;
- three-persona equal-entitlement hash proof;
- early/final as-of restatement;
- incomplete landed-cost refusal;
- Definitions and Audit;
- passing evaluation summary.

Video checklist:

- readable cursor/zoom and captions;
- one continuous primary flow under five minutes;
- disclosure spoken and visible;
- no edited jump hides setup, errors, or role changes;
- fallback recording ready.

Deck checklist:

- PS5 problem and disagreement;
- product thesis;
- one-manufacturer data design and limitations;
- ontology/semantic architecture;
- metric contract and evidence envelope;
- persona parity;
- evaluation/security;
- demo/results;
- explicit claims/non-claims;
- deployment/reproducibility.

## Demo recovery

If Cortex Analyst/Agent is unavailable, use the labelled local fixture mode or
call the deterministic `ASK_METRIC` verified-question path. The same frozen
envelopes, trace, definitions, persona-parity hashes, and as-of replay remain
demoable. State that arbitrary new natural-language questions are disabled in
fallback mode. If viewer-context enforcement is not proven, use an explicitly
equal-entitlement demo cohort and do not claim production-grade per-user row
security.

## Submission claims

Use:

- “governed reference implementation”;
- “simulated manufacturer”;
- “deterministically evaluated”;
- “versioned semantic contracts”;
- “evidence-backed conversational analytics”;
- “same-scope persona parity.”

Do not use:

- “real-time control tower” unless freshness proves it;
- “customer validated”;
- “industry benchmark”;
- “improved OTD/cost/inventory”;
- “causal AI”;
- “zero hallucination”;
- “autonomous optimization”;
- “digital twin of a real company.”

## Judge attack responses

### “It is synthetic.”

Correct. The statement evaluates governed definitions and consistency, not a
predictive model. Every record is labelled. Golden truth lets us prove formula,
lineage, identity, temporal, and persona behavior exactly. We do not claim real
business outcomes.

### “Why use an LLM?”

It removes the need to know schema vocabulary. It is bounded to entity/scope
interpretation, governed retrieval, and explanation. SQL contracts—not the
LLM—calculate the metrics.

### “Can teams choose different definitions?”

They can propose a versioned contract change. They cannot silently redefine a
published metric through a report or prompt.

### “What happens with incomplete data?”

Coverage and exclusions are returned with the number; critical unresolved
inputs cause abstention or incomplete status instead of guessing.

### “Can this connect to real systems?”

The source mappings, event vocabulary, identities, semantic contracts, and
security model are designed as adapters. The hackathon does not claim that a
real SAP/Oracle/TMS mapping has been completed.

