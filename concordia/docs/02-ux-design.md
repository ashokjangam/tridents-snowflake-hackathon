# UX and interaction design

## Design position

Concordia is one calm business application with evidence in context. It is not
a wall of dashboards and not two products split between “business” and
“engineering.”

Progressive disclosure:

1. **Answer** — what the business user needs now.
2. **Why** — drivers, exclusions, and affected entities.
3. **Evidence** — source rows, calculation, provenance, and freshness.
4. **Governance** — owner, version, grain, lineage, query, and audit.

The primary interface avoids SQL, warehouse names, object names, and model
terminology. Technical reviewers can open those details without leaving the
answer.

## Information architecture

### Ask

Default conversational workspace. Questions, clarification, governed answers,
follow-ups, saved evidence, and role-aware suggested prompts.

### Operations

A focused exceptions list and dependency ribbon. No generic executive
dashboard. Summary measures are limited to:

- customer commitments affected;
- units affected;
- unresolved records affecting coverage.

These are governed diagnostic counts over the selected answer's contribution
set, not additional enterprise KPIs. Their grains and count rules live in the
semantic contract; Streamlit does not calculate them.

### Definitions

Searchable ontology and metric catalog. Each definition shows plain-language
meaning before technical implementation.

### Audit

Question → interpretation → scope → semantic query → result → evidence chain.
Business users see History; steward/auditor roles see full audit fields.

## Shell

Top bar:

- Concordia mark and tagline;
- company and scenario scope;
- as-of timestamp;
- freshness status;
- role/persona;
- permanent “Simulated manufacturer” indicator.

Left navigation:

- Ask;
- Operations;
- Definitions;
- Audit.

The answer column remains the visual focus. An evidence drawer opens on the
right at desktop widths and as a full-screen sheet on mobile.

## Ask page

Opening copy:

> What decision are you trying to understand?

Supporting copy:

> Ask about suppliers, parts, plants, inventory, shipments, orders, customers,
> or a governed metric.

Role-aware prompts:

- VP: “Why did outbound customer OTD change in May 2026?”
- Planner: “Which parts constrain MM-440 fulfillment at Dayton?”
- Procurement: “Which supplier receipts missed their acknowledged promise?”
- Logistics: “Which delivery attempts explain Northeast lateness?”

### Answer anatomy

1. One-sentence direct answer.
2. Primary metric with id/version, value, numerator, and denominator.
3. Scope chips: period, as-of, product, plant, region, customer/supplier.
4. Provenance and freshness badges.
5. Ranked contributing factors.
6. Exclusions and coverage.
7. Caveat/refusal where required.
8. Controls: See evidence, Open trace, Open definition, Ask follow-up.

### Clarification

Concordia never silently resolves ambiguous terms.

Example:

> “OTD” can mean inbound supplier delivery or outbound customer delivery.
> Which one should I use?

Options:

- Supplier OTD
- Customer OTD
- Show both without combining them

### Refusal states

Missing data:

> I cannot calculate a complete landed cost because duty is unresolved for part
> of the accepted quantity. Coverage is shown below.

The percentage is populated from the frozen fixture envelope, never hard-coded.
The UI may offer a clearly labelled known-cost diagnostic; it does not display
that diagnostic as the canonical landed-cost value.

Unsupported inference:

> The records show that low ratings and late deliveries occurred in the same
> locality. They do not establish that ratings caused the delays.

Out-of-scope:

> Concordia does not forecast next-quarter demand. It can show historical order,
> shipment, and inventory definitions consistently.

Permission:

> You can view the service result, but your role cannot view supplier unit cost.

## Operations page

Use a ranked exception list, not multiple independent charts.

Each row shows:

- business issue;
- affected customer commitments;
- affected units;
- first visible event;
- last refreshed time;
- evidence quality;
- unresolved-data impact.

Selecting an issue opens the dependency ribbon.

## Dependency ribbon

Use six stable stages:

Supplier → Part → Plant → Shipment → Order → Customer

This is a navigational arrangement, not a claim that shipment chronologically
precedes order.

Rules:

- show only the selected evidence path;
- group excess nodes as “+12 orders”;
- use edge width for affected quantity;
- label edge type: supplies, consumed by, produced at, allocated to, fulfills,
  ships to;
- distinguish proven event links from “may affect” associations;
- expand one step at a time;
- provide a text equivalent for keyboard and screen-reader users.

Avoid force-directed graphs.

## Definitions page

Metric card:

- business name;
- metric id/version;
- plain-language definition;
- value, unit, grain, time basis, and timezone;
- formula rendered in words;
- numerator and denominator;
- included and excluded populations;
- owner and approval status;
- current version and change reason;
- rejected aliases;
- known limitations;
- technical SQL/object details in a collapsed section.

Ontology card:

- entity definition;
- canonical identifier;
- source aliases;
- valid relationships;
- cardinality;
- effective dates;
- unresolved mappings.

## Audit page

Search by:

- question;
- metric;
- evidence id;
- source record;
- entity;
- user;
- date.

Timeline:

1. question submitted;
2. ambiguity resolved;
3. scope applied;
4. semantic query generated or verified query selected;
5. allowlist decision;
6. query executed;
7. answer envelope created;
8. narrative created or suppressed;
9. evidence viewed/exported.

## Evidence drawer

Sections:

- **Answer contract** — metric, version, scope, formula hash.
- **Calculation** — numerator, denominator, exclusions, coverage.
- **Source evidence** — source-friendly name, source key, event/document time.
- **Resolution** — identity, UOM, currency, timezone mappings.
- **Freshness** — last visible event, pipeline watermark, SLA.
- **Technical** — Snowflake query id, governed object, lineage reference.

Every source card says `Synthetic ERP`, `Synthetic MES`, `Synthetic WMS`,
`Synthetic TMS`, or `Synthetic CRM`.

## Role behavior

Roles change:

- prompt suggestions;
- default explanation ordering;
- row-level scope;
- cost visibility;
- access to technical/audit detail.

Roles do not change:

- metric id/version;
- formula;
- numerator and denominator logic;
- as-of semantics;
- source precedence;
- exclusion rules.

## Visual system

Personality: assured, precise, calm, evidence-led.

Palette:

- deep ink/navy for structure;
- warm ivory for the primary canvas;
- teal for governed/verified states;
- amber for incomplete/stale/ambiguous states;
- restrained red for confirmed exception only;
- slate for metadata.

Avoid gradients, neon AI styling, glassmorphism, excessive card borders, and
decorative network graphics.

Typography:

- contemporary humanist sans for interface;
- optional restrained serif for the Concordia wordmark only;
- body size at least 16px;
- tabular numerals for metrics;
- direct labels on charts.

Charts:

- metric bridge/waterfall for changes;
- horizontal ranked bars for contributors;
- compact time series for as-of/restatement;
- no pie charts or gauges;
- always label unit, source, period, and calculation.

## Accessibility

- WCAG 2.2 AA contrast;
- keyboard-complete navigation;
- visible focus;
- no color-only encoding;
- 44px touch targets;
- chart summaries and accessible tables;
- reduced-motion support;
- focus trapping/return for drawers;
- live-region announcement when an answer completes;
- locale-aware numbers and dates.

## Responsive behavior

Desktop:

- persistent navigation;
- 760–880px answer column;
- 360–420px evidence drawer.

Tablet:

- collapsed navigation;
- overlay evidence drawer.

Mobile:

- bottom navigation for Ask, Operations, Definitions, Audit;
- evidence becomes full-screen;
- ribbon scrolls by stage with Previous/Next controls;
- composer stays sticky.

## Required UI states

- loading stages;
- empty/new user;
- clarification;
- governed answer;
- partial answer;
- stale answer;
- conflicting source systems;
- unsupported question;
- permission denial;
- query error with preserved question;
- narrative suppressed because it introduced unsupported numbers;
- local fixture mode;
- Snowflake unavailable.

## Five-minute UI demo

1. Nora asks the hero question.
2. Concordia returns customer OTD with scope and permanent simulation badge.
3. Open Why: partial fulfillment, quality hold, and failed Northeast delivery.
4. Open trace: supplier through affected customers.
5. Switch through planning, procurement, and logistics under equal entitlement:
   exact metric fields and evidence hash match; explanation emphasis changes.
6. As a cost-entitled procurement user, rewind as-of: late freight restates
   landed cost but not customer OTD.
7. Ask “What is OTD?” and show the clarification.
8. Ask to treat missing duty as zero and show the refusal.
9. Open Governance and show definition/version/query/evidence id.

