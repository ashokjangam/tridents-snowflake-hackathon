# Simulation and data contract

## Purpose

Generate a causally coherent fictional manufacturer and project it into five
messy source systems. The hidden world supplies evaluation truth. Product logic
must resolve source records without reading hidden truth.

## Locked identity

- Contract: `CONCORDIA_SIM_V1`
- Manufacturer: Meridian Motion
- Master seed: `20261002`
- Reporting currency: USD
- Operational period: 2025-01-01 through 2026-06-30
- Hero reporting period: 2026-05-01 through 2026-05-31
- Hero early recorded-as-of: 2026-06-05T23:59:59Z
- Hero final recorded-as-of: 2026-07-15T23:59:59Z
- Hero entities: finished product MM-440, Apex Bearings, Dayton plant, and
  Northeast customer region
- Hero benchmark scope: finished product MM-440 for May 2026. This is not the
  MM-440 family and supersedes the PRD wording “MM-440 family.”
- All timestamps stored in UTC plus source/local timezone
- Money in integer USD cents, rounded half-even
- Quantities as `Decimal` values quantized to six base-UOM places, half-even

Changing formula, entity structure, event semantics, distribution family, or
seed derivation requires a contract version change. Metric version remains
`1.0.0` because these rules were frozen before any result was calculated.

## Frozen seed, numerics, and hashes

Master seed string: `20261002`.

Each independent stream seed is the first 8 bytes of
`SHA-256("CONCORDIA_SIM_V1|20261002|<stream>")`, interpreted as a big-endian
unsigned integer. The UTF-8 string is hashed. The digest bytes are used, not
the hex text. That integer seeds
`numpy.random.Generator(numpy.random.PCG64(seed_uint64))` on NumPy 2.2.6.
NumPy’s `PCG64` constructor passes the integer through `SeedSequence`. The
pinned NumPy version is part of the freeze.

Stream names, in this order:

1. `demand`
2. `supply`
3. `production`
4. `quality`
5. `transit`
6. `commercial`
7. `feedback`
8. `defects`

Evidence hashes and hidden-truth hashes are lowercase hex SHA-256 digests of
canonical JSON:

- UTF-8;
- object keys sorted by Unicode code point;
- arrays keep their order;
- separators are comma and colon with no extra whitespace;
- money is a JSON integer of USD cents;
- quantities are JSON strings with exactly six digits after the decimal point;
- no `NaN` or `Infinity`.

Product code must not read hidden truth to decide that a cost document should
have existed.

## Origin vocabulary

Allowed:

- `SYNTHETIC_ERP`
- `SYNTHETIC_MES`
- `SYNTHETIC_WMS`
- `SYNTHETIC_TMS`
- `SYNTHETIC_CRM`
- `DERIVED_FROM_SYNTHETIC`

Evaluation-only, forbidden from `LAND`, `CORE`, `GOV` answer objects, `APP`, and
all product envelopes:

- `EVAL_GOLD`
- `INJECTED_DEFECT`

`OBSERVED` is forbidden.

## Population

Frozen for `CONCORDIA_SIM_V1`:

- 3 plants;
- 3 distribution centres;
- 40 suppliers;
- 200 parts;
- 75 BOM parents, each with at least one effective-dated revision;
- 24 customers with sold-to/ship-to hierarchy;
- 60 lanes.

The BOM-parent count of 75 is inside the earlier planning range of 60–90
parents/revisions. Scale is not a quality metric. Every named scenario needs a
hand-checkable fixture.

## Facilities and calendars

Plants:

- Dayton, United States, `America/New_York`;
- Reno, United States, `America/Los_Angeles`;
- Stuttgart, Germany, `Europe/Berlin`.

Distribution centres:

- Newark, United States, `America/New_York`;
- Oakland, United States, `America/Los_Angeles`;
- Hamburg, Germany, `Europe/Berlin`.

The default governed calendar is Monday through Friday. A missing calendar
excludes the affected row. Named shutdowns are the only extra closed days.
Dayton has one named shutdown on 2026-05-25. That date is not an imported
holiday calendar.

Hero supplier geography for the landed-cost receipt: Apex Bearings has a
supplier site in the United States shipping to Dayton, so that receipt is
same-country.

## Hidden world

`SIM.TRUTH_EVENT` contains:

- event id/type;
- occurred time;
- canonical entities;
- exact quantities/currencies;
- causal parent event ids;
- scenario ids;
- true identity crosswalk;
- true event outcome.

Only the test role can read it.

The product receives rendered ERP/MES/WMS/TMS/CRM records with distortions,
delays, duplicates, revisions, and omissions.

## Source-system projections

### ERP

- vendor and material masters;
- supplier-part agreements;
- POs/schedule lines;
- goods receipts;
- AP invoices;
- sales orders;
- original/revised promise records and approval timestamps;
- Incoterm and contractual completion location;
- customer-approved short-close/cancellation records;
- source currencies and financial dates.

Distortions: duplicate vendor ids, current-state overwrite, inconsistent date
formats, late invoice posting, stale FX.

### MES

- BOM/routing versions;
- production orders;
- component issues;
- completion, scrap, and hold events;
- finished-lot births.
- quality disposition reason and accountable party.

Distortions: plant-local naive timestamps, alternate item codes, delayed ERP
confirmation.

### WMS

- license plates/lots;
- bins;
- receipts, moves, allocation, pick, hold, release;
- inventory snapshots.
- governed facility calendars and gross physical on-hand semantics.

Distortions: case versus each, reused lot ids by plant, duplicate moves, book
versus physical disagreement.

### TMS

- shipment, line, carrier, ASN, tracking, delivery attempts, POD;
- ready-for-pickup and ship-confirmation events;
- freight and accessorial invoices.

Distortions: multiple shipment identifiers, missing timezone, late POD,
misdelivery correction, ETA overwritten.

### CRM

- customer hierarchy;
- original promise and revisions;
- customer hold/short-close approvals with effective timestamps;
- service cases;
- ratings and complaints.

Distortions: merged customer names not yet reflected in ERP, overwritten
promise, unstructured complaint templates.

## Causal state machines

### Purchase schedule

`OPEN → ACKNOWLEDGED → IN_TRANSIT → PART_RECEIVED → RECEIVED → CLOSED`

Alternative outcomes: `CANCELLED`, `REJECTED`, `RETURNED_TO_SUPPLIER`.

### Production order

`PLANNED → RELEASED → STARTED → HELD → COMPLETED → CONFIRMED → CLOSED`

Alternative outcomes: `CLOSED_SHORT`, `SCRAPPED`.

### Sales-order line

`DRAFT → BOOKED → PROMISED → ALLOCATED/PART_ALLOCATED → PICKED → SHIPPED → DELIVERED → INVOICED → CLOSED`

Alternative outcomes: `CANCELLED`, `SHORT_CLOSED`, `RETURN_OPEN → CREDITED`.

### Shipment

`PLANNED → TENDERED → PICKED_UP → IN_TRANSIT → OUT_FOR_DELIVERY → DELIVERED`

Alternative outcomes: `FAILED_ATTEMPT`, `MISDELIVERED`, `RECONSIGNED`,
`DAMAGED`, `LOST`.

### Lot

`PLANNED → IN_TRANSIT → DOCK → QC → AVAILABLE → ALLOCATED → PICKED → SHIPPED`

Alternative outcomes: `HOLD`, `SCRAP`, `RETURNED_TO_SUPPLIER`.

Quantities are conserved through explicit split, merge, consume, produce,
ship, return, and adjustment events.

The hero fixture must deterministically contain:

- a partial receipt and supplier-versus-plant quality disposition;
- a MM-440 partial shipment and final delivery;
- a Northeast failed/misdirected delivery;
- an original and revised promise;
- a `DAP` contractual completion milestone for the hero sales lines;
- a separate same-country buyer-responsible `EXW` inbound receipt at Dayton
  from Apex Bearings.

The hero landed-cost receipt is that `EXW` receipt. It is not the `DAP` sales
milestone. At the early recorded-as-of, freight and brokerage obligations are
visible and their invoice amounts are not. The final recorded-as-of adds those
amounts. Customer OTD does not move unless delivery evidence moves. Missing
duty is a separate cross-border fixture, not the reason this hero result is
incomplete.

The hero customer-OTD explanation is the May contribution drivers for finished
product MM-440. The early and final recorded-as-of customer-OTD values stay
equal when delivery evidence is unchanged. The landed-cost hero is the as-of
restatement.

Before UI implementation, the fixture manifest freezes each benchmark
question's exact numerator, denominator, status, exclusions, and evidence ids
for both as-of timestamps. Those fixtures are hand-specified. The simulator
must reproduce them from visible source records, not by copying hidden truth
into the metric result.

## Scenario families

Always-on integration defects:

- identity aliases/collisions;
- UOM mismatches;
- currency/FX differences;
- timezone differences;
- late extracts;
- source revisions.

Named business scenarios:

1. baseline operations;
2. supplier disruption;
3. partial receipt and peak-demand partial fulfillment;
4. incoming quality-hold cascade;
5. BOM revision/effectivity;
6. regional/locality delivery delay;
7. promise revision;
8. failed delivery, misdelivery, return, and complaint;
9. landed-cost shock and late invoices;
10. identity collision;
11. broken UOM/currency/timezone;
12. late data and restatement;
13. plant shutdown/customer receiving calendar;
14. rating divergence: poor rating with good OTD and vice versa.

## Distribution discipline

Distributions are design assumptions, not empirical estimates.

Use independent deterministic RNG streams named:

- `demand`;
- `supply`;
- `production`;
- `quality`;
- `transit`;
- `commercial`;
- `feedback`;
- `defects`.

Suggested families:

- order lines: zero-truncated negative binomial;
- quantities/costs: lognormal then rounded to pack/UOM;
- supplier and transit lead times: tier/lane-specific lognormal mixtures;
- quality/reject/failed-delivery events: conditional Bernoulli;
- ratings: ordinal response conditioned on visible service outcomes plus noise;
- FX: synthetic bounded stochastic path clearly labelled non-market.

Never tune distributions to make a headline metric look impressive.

## Realism rules

- Regional delays apply to lanes/local calendars, not arbitrary customer labels.
- Customer ratings are downstream feedback and never define OTD.
- Late invoices change cost knowledge, not physical delivery history.
- Promise revisions are append-only and do not rewrite original promise.
- A quality hold reduces available inventory.
- Supplier-caused and plant-caused holds are distinct.
- Returns can follow on-time delivery.
- Failed delivery attempt is not delivered.
- Production cannot consume a component before receipt/release.
- Finished goods cannot ship before production or opening inventory.
- BOM effectivity determines which part demand exists on each date.

## Golden invariants

- all foreign keys resolve in truth;
- no negative physical inventory;
- received quantity is conserved across available/held/rejected/consumed;
- consumed components reconcile to output and scrap under BOM/routing policy;
- shipped ≤ picked ≤ allocated, except explicit controlled over-ship;
- delivered ≤ shipped;
- returned ≤ delivered;
- promise revisions form one ordered chain;
- every cost has currency/economic date;
- every projected row maps to truth or is an explicitly injected orphan defect;
- same seed/version/contract produces identical truth hashes.

## Projection defects

The product must detect or abstain on:

- duplicate source rows;
- missing foreign key;
- conflicting identity aliases;
- wrong/missing UOM conversion;
- timezone-naive event;
- impossible event chronology;
- stale/missing FX;
- missing landed-cost component;
- overwritten promise;
- source event arriving out of order;
- book/physical inventory disagreement.

The hidden defect catalog is evaluation-only.

## Data volume policy

Generate event milestones and meaningful history, not decorative billions of
rows. Target enough data to:

- show every scenario more than once;
- support locality, product, plant, supplier, and customer slices;
- demonstrate restatement and bitemporal queries;
- remain locally reproducible and hand-auditable.

## Synthetic disclosure

Every page and export must state:

> Simulated manufacturer. No record is observed customer data.

Permitted conclusion:

> Concordia resolves the published metric contract consistently on the
> simulated source systems.

Forbidden conclusion:

> Concordia improved a real manufacturer's OTD, inventory, or cost.

