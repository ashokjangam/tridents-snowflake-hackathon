# Product requirements document

## 1. Executive summary

Concordia is a governed conversational analytics product for supply-chain
leaders. It converts inconsistent records from simulated ERP, MES, WMS, TMS,
and CRM systems into a shared ontology and five published metrics.

Users ask ordinary business questions. Concordia returns a deterministic answer,
its business definition, numerator, denominator, scope, as-of time, freshness,
exclusions, and supporting records. Planning, procurement, logistics, and
leadership use the same metric engine.

## 2. User problem

The same label often hides different calculations:

- Procurement calls supplier receipt performance OTD.
- Logistics calls customer delivery performance OTD.
- One analyst uses original promises; another uses revised promises.
- One team counts partial deliveries; another requires complete lines.
- One landed-cost report treats missing duty as zero.
- One inventory report includes quality holds and in-transit stock.

The problem is not access to data alone. It is uncontrolled business meaning.

## 3. Goals

### G1 — Shared definitions

Publish one authoritative contract for every supported metric and ontology
relationship.

### G2 — Governed natural language

Allow users to ask questions without allowing an LLM to create a formula,
silently choose an ambiguous definition, or query raw source tables.

### G3 — Evidence-backed answers

Every number must expose its scope, formula version, numerator, denominator,
freshness, origin, exclusions, and evidence identifiers.

### G4 — Cross-persona identity

For identical scope and entitlement, planning, procurement, and logistics must
receive the same metric result regardless of wording or role.

### G5 — Realistic integration

Demonstrate identity, unit, currency, timezone, late-data, effectivity, and
source-conflict problems representative of real ERP/MES/WMS/TMS/CRM estates.

## 4. Non-goals

- Predict demand, failures, delays, churn, or returns.
- Recommend safety stock, suppliers, routes, or expedite decisions.
- Execute transactions in source systems.
- Reproduce a full enterprise suite.
- Support arbitrary user-defined metrics in v1.
- Present generated performance as a benchmark.

## 5. Personas and jobs

### Nora Hale — VP Supply Chain

Needs one defendable answer for the Monday operating review and a concise
explanation of why it changed.

### Priya Shah — Supply Planner

Needs product/plant inventory coverage, BOM effectivity, partial fulfillment,
and customer-order impact.

### Marcus Webb — Procurement Manager

Needs inbound supplier OTD, receipt quality, incomplete landed cost, and the
parts and plants exposed.

### Elena Voss — Logistics Manager

Needs outbound customer OTD, delivery attempts, regional exceptions, shipment
status, and affected customers.

### Jordan Ellis — Data Steward / Auditor

Needs the owner, version, grain, formula, lineage, exclusions, unresolved
records, query identifier, and change history behind an answer.

## 6. Hero scenario

Meridian Motion manufactures industrial drive assemblies. In the hero period:

1. supplier Apex Bearings partially delivers a revised bearing;
2. a subset fails incoming inspection;
3. a BOM revision makes the replacement bearing effective at one plant;
4. available inventory becomes insufficient;
5. production order completion slips;
6. some orders are partially shipped;
7. a Northeast lane has failed delivery attempts;
8. customer promise dates are revised in CRM;
9. freight and brokerage invoices arrive after physical delivery;
10. customer ratings fall for one locality, while another low rating is
    unrelated to OTD.

Nora asks:

> Why did outbound customer OTD for the MM-440 family change in May 2026?

Concordia distinguishes:

- promise-date changes;
- plant quality holds;
- partial fulfillment;
- delivery-attempt failures;
- unresolved records;
- and late cost invoices that do not affect delivery timeliness.

The product does not call every association causal. A relationship is described
as causal only when the simulator's visible event chain establishes it.

## 7. Functional requirements

### FR1 — Ontology

Represent Supplier, Supplier Site, Part, Product, BOM Revision, Plant,
Warehouse/DC, Lot, Production Order, Purchase Order, Receipt, Shipment, Sales
Order, Customer, Promise, Delivery Event, Invoice, Cost Component, Return,
Complaint, and Rating.

### FR2 — Canonical relationships

Support typed, effective-dated relationships including:

- `SUPPLIES`;
- `COMPONENT_OF`;
- `SUBSTITUTES_FOR`;
- `CAPABLE_OF_PRODUCING`;
- `RECEIVED_FROM`;
- `HELD_AT`;
- `CONSUMES`;
- `PRODUCES`;
- `EXECUTED_AT`;
- `ALLOCATED_TO`;
- `CONTAINS`;
- `FULFILLS`;
- `PLACED`;
- `DELIVERED_TO`;
- `RETURNED_AGAINST`;
- `PROMISES`;
- `COST_OF`;
- `FEEDBACK_ON`;
- `SAME_AS`.

The ontology contract is authoritative for relationship semantics.

### FR3 — Metrics

Publish:

- inbound supplier OTD;
- outbound customer OTD;
- unit fill rate;
- days inventory;
- landed cost per accepted unit.

### FR4 — Conversation

Interpret metric, entities, scope, period, comparison, and as-of time. Ask for
clarification when “OTD,” “inventory,” “landed cost,” or scope is ambiguous.

### FR5 — Answers

Return:

- direct answer;
- why it matters;
- value and unit;
- metric id/version;
- numerator and denominator;
- period and as-of;
- applied scope and defaults;
- freshness and coverage;
- exclusions and unresolved records;
- evidence id and source systems;
- caveats.

### FR6 — Trace

Provide a focused dependency ribbon across supplier, part, plant, shipment,
order, and customer. It must show only entities supporting the selected answer
and provide an accessible list equivalent.

### FR7 — Definitions

Expose plain-language and technical formulas, owner, version, grain,
inclusions, exclusions, source fields, rejected aliases, and change history.

### FR8 — Persona parity

Role changes suggested questions, explanation emphasis, row entitlement, and
available actions. It must not change a metric formula.

### FR9 — As-of replay

Users can compare answers before and after late-arriving events. The UI must
identify which records restated the result.

### FR10 — Audit

Record question, interpreted intent, scope, semantic object, query id, result
hash, evidence snapshot, user, role, model pin, and timestamp.

### FR11 — Refusal

Refuse or abstain when:

- the requested metric is unsupported;
- identity, UOM, timezone, or currency is unresolved;
- landed cost is incomplete beyond the contract's coverage rule;
- the question requests a forecast, optimization, or market benchmark;
- SQL would bypass approved semantic objects;
- permission does not allow the requested scope or cost detail.

## 8. User stories and acceptance

### US1 — Same answer

Given the same scope, period, as-of, and entitlement, when planner, procurement,
and logistics users ask paraphrases of a benchmark question, then metric id,
version, numerator, denominator, value, exclusions, and evidence hash match.

### US2 — OTD ambiguity

When a user asks only “What is OTD?”, Concordia asks whether they mean inbound
supplier OTD or outbound customer OTD before returning a number.

### US3 — Partial fulfillment

When an order is partially shipped, unit fill rate reflects fulfilled quantity
while outbound OTD follows the final-completion rule in the metric contract.

### US4 — Locality

When a user asks why one locality is late, Concordia applies that locality as a
filter and shows lane, delivery-attempt, and customer evidence without changing
the enterprise metric definition. Locality is a governed geography hierarchy
node, not a free-text customer attribute.

### US5 — Ratings

When a user asks whether poor ratings caused lateness, Concordia states that
ratings are associated customer feedback and do not define OTD or establish
causation.

### US6 — Late freight

When an invoice arrives after the first as-of, landed cost changes at the later
as-of while delivery metrics remain unchanged unless delivery evidence also
changed.

### US7 — Data problem

When a case-to-each conversion is unresolved, affected rows are excluded or the
answer abstains according to contract; the UI never guesses a conversion.

### US8 — Evidence

When the user opens Evidence, every headline number is traceable to governed
metric contributions and source records.

## 9. Product requirements by judging criterion

### Real-world relevance

- Model real source-system boundaries and business edge cases.
- Use standards-informed event and entity vocabularies without claiming
  certification or conformance.
- Demonstrate problems familiar to operating teams.
- Show an onboarding mapping contract for future real sources.
- Permanently disclose simulation.

### Technical execution

- Deterministic contracts and bitemporal event handling.
- Idempotent ingestion and replay.
- Semantic views and constrained conversational access.
- Evidence envelopes and source lineage.
- Automated contract, parity, metamorphic, and security tests.

### Completeness

- Full required entity chain.
- All canonical metrics.
- All three personas.
- Conversational analytics.
- Definitions, evidence, ambiguity handling, and audit.
- Local preview and Snowflake deployment path.

## 10. Success gates

- 100% exact golden-fixture agreement.
- 100% persona parity for same-scope benchmark prompts.
- 100% headline numbers carry evidence and metric metadata.
- Zero `OBSERVED` origins.
- Zero LLM-authored metric formulas.
- Zero unrestricted raw-table queries.
- All unsupported benchmark prompts abstain.
- Re-running ingestion does not change counts or results.
- Same seed and contract version reproduce identical golden hashes.

## 11. Risks

- A polished simulator can still look like a toy if edge policies are shallow.
- Excessive entities can dilute the five locked canonical metrics.
- A chat interface can obscure governance unless metadata is one click away.
- “Causal trace” language can overstate association.
- Streamlit session identity must be validated before claiming row security.
- Snowflake feature availability varies by account and region.

