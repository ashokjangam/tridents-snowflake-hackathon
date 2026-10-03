# Ontology and metric contract

Status: **normative**. Implementation must not change these definitions without
a versioned contract change and updated tests.

## Ontology principles

- Business concepts are independent of source column names.
- Relationships are typed, effective-dated, and evidence-backed.
- Many-to-many bridge entities are explicit.
- Event chronology does not follow the visual left-to-right ribbon.
- Identity uncertainty is represented, not hidden.
- Source records remain available for audit.

## Core entities

### Party

Organization participating as manufacturer, supplier, supplier site, customer,
customer ship-to, carrier, broker, or internal legal entity.

Canonical key: `PARTY_ID`.

### Part/Product

Purchased component, subassembly, packaging material, or finished product.

Canonical key: `ITEM_ID`. External identifiers and source SKUs are aliases.

### Facility

Plant, warehouse, distribution centre, dock, supplier site, or customer
ship-to. Includes role, timezone, geography, and effective dates.

Canonical key: `FACILITY_ID`.

### BOM revision

Effective-dated parent/component structure with quantity, UOM, scrap factor,
substitute policy, and revision.

### Lot/serial

Physical identity and genealogy of received components, work in process, and
finished goods.

### Business document

Purchase order/schedule line, sales order/line, ASN, shipment, invoice,
quality disposition, return, or credit.

Promise revisions, cost components, complaints, and ratings are first-class,
effective-dated records linked to the business document or party they describe.

### Event

Append-only operational occurrence: receiving, inspection, hold, release,
consumption, production, aggregation, shipping, delivery attempt, delivery,
return, invoice, or correction.

## Canonical relationships

- Supplier `SUPPLIES` Part.
- Part `COMPONENT_OF` BOM revision.
- Part `SUBSTITUTES_FOR` Part under an effective approved policy.
- Plant `CAPABLE_OF_PRODUCING` Product.
- Lot `RECEIVED_FROM` Supplier.
- Lot `HELD_AT` Facility.
- Production order `CONSUMES` component Lot.
- Production order `PRODUCES` finished Lot.
- Production order `EXECUTED_AT` Plant.
- Finished Lot `ALLOCATED_TO` sales-order line.
- Shipment line `CONTAINS` Lot.
- Shipment `FULFILLS` sales-order line.
- Customer `PLACED` sales order.
- Shipment `DELIVERED_TO` customer ship-to.
- Return `RETURNED_AGAINST` sales-order line and delivery.
- Promise revision `PROMISES` sales-order line.
- Cost component `COST_OF` receipt/shipment/accepted lot.
- Complaint/rating `FEEDBACK_ON` order/shipment/delivery.
- Source identifier `SAME_AS` canonical entity only through an approved mapping.

These uppercase names are the normative relationship enum. UI labels such as
“supplies,” “consumed by,” “packed in,” “ships to,” and “ordered by” are display
aliases only.

## Hierarchies

- Product family → finished product → subassembly → component.
- Company → region → plant/DC → storage/dock location.
- Supplier category → supplier → supplier site.
- Customer region → account → ship-to.
- Geography → country → region → locality → postal zone.
- Year → quarter → month → day.

## General metric rules

- Ratios use `SUM(numerator) / SUM(denominator)`.
- Never average pre-aggregated percentages.
- Store numerator, denominator, exclusions, coverage, grain, and as-of.
- Zero denominator returns null with a reason.
- An unresolved UOM, identity, timezone, or required currency conversion does
  not enter numerator or denominator and increments excluded coverage.
- Ratios store exact contribution values; display rounding is four decimals.
- The default reporting currency is USD, but source currency remains visible.
- Money is stored as integer USD cents and rounded half-even. Quantities are
  `Decimal` values quantized to six base-UOM places, half-even. Evidence hashes
  are SHA-256 of canonical JSON, as frozen in the simulation contract.
- Metric version `1.0.0` is unchanged. These rules were frozen before any
  result was calculated.
- Every metric uses the source revision for which
  `RECORDED_FROM <= RECORDED_AS_OF < COALESCE(RECORDED_TO, infinity)` and
  `VISIBLE_AT <= RECORDED_AS_OF`.
- Period membership uses the metric-specific business date in the relevant
  facility/customer timezone, not UTC date.
- Business-day rules use the governed calendar attached to the receiving
  facility; if absent, the affected row is excluded.

Closed answer statuses are:

- `COMPLETE`;
- `INCOMPLETE`;
- `ZERO_DENOMINATOR`;
- `ZERO_DEMAND`;
- `CLARIFY`;
- `ABSTAIN`;
- `FORBIDDEN`;
- `STALE`.

Exact values are compared in contracts/tests; rounding is presentation only.

## M1 — Inbound supplier OTD

Metric id: `INBOUND_SUPPLIER_OTD`

Version: `1.0.0`

Business question:

> Did the supplier complete the accepted quantity for each PO schedule line by
> the supplier commitment date?

Grain: eligible purchase-order schedule line.

Commitment:

- acknowledged supplier promise visible within two business days of PO issue;
- otherwise buyer-requested date;
- a reconfirmation after physical receipt cannot rewrite the commitment.

The two-day window uses the receiving facility's governed business calendar.
The commitment date is interpreted in that facility's timezone.

Completion clock: first time cumulative accepted quantity reaches ordered
schedule quantity at the receiving plant.

Accepted means received and released from supplier-caused quality hold.

Numerator: eligible lines completed on or before commitment.

Denominator: eligible lines whose commitment falls in the period.

Policies:

- partial early receipt is not a line hit;
- supplier-caused rejected quantity does not count;
- buyer cancellation before commitment is excluded;
- supplier-caused late cancellation is a miss;
- future open lines are excluded;
- past-due incomplete lines are misses;
- plant-caused post-acceptance hold does not fail the supplier;
- unresolved supplier/UOM/timezone is excluded and disclosed.
- disposition reason must identify supplier-caused versus plant-caused holds;
  missing disposition makes the affected line unresolved.

## M2 — Outbound customer OTD

Metric id: `OUTBOUND_CUSTOMER_OTD`

Version: `1.0.0`

Business question:

> Did the customer receive the complete committed quantity by the original
> accepted promise date?

Grain: eligible sales-order line.

Promise: original accepted customer promise. Revised-promise performance is a
separate diagnostic and cannot replace this contract.

Completion clock:

- `EXW`/`FCA`: first valid ready-for-pickup time at the named origin;
- `DAP`/`DDP`: first valid proof-of-delivery time at the
  effective customer ship-to where cumulative accepted delivered quantity
  reaches the required quantity.

The completion and promise dates use the governed timezone/calendar of the
contractual completion location. V1 supports only `EXW`, `FCA`, `DAP`, and
`DDP`. A missing/unsupported Incoterm, timezone, or calendar excludes the
affected line and returns `INCOMPLETE` with coverage. If no eligible resolved
line remains, return `ABSTAIN`; never guess a milestone.

Numerator: eligible lines completed on or before promise.

Denominator: eligible lines with promise date in the period.

Policies:

- ship date is not delivery date;
- failed or misdirected delivery attempts do not count;
- partial deliveries count only when cumulative required quantity completes;
- customer-approved short close changes required quantity only when approved
  before the promise;
- a customer-caused hold is excluded only when a pre-promise, source-recorded
  hold interval covers the contractual completion deadline; otherwise it
  remains eligible;
- later returns do not restate OTD;
- the answer displays whether origin pickup or destination delivery is the
  governed milestone.

Status when rows are excluded:

- a missing or unsupported Incoterm, timezone, or calendar excludes that line
  and makes the answer `INCOMPLETE` while any resolved eligible line remains;
- if no resolved eligible line remains and at least one line was excluded for
  Incoterm, timezone, or calendar, return `ABSTAIN`;
- other exclusions, such as unresolved identity or UOM, stay out of the ratio
  and are disclosed. If they are the only reason the eligible set is empty,
  return `ZERO_DENOMINATOR`.

## M3 — Unit fill rate

Metric id: `UNIT_FILL_RATE`

Version: `1.0.0`

Business question:

> What proportion of ordered units was ship-confirmed, independent of
> timeliness?

Population: sales-order lines whose original requested ship date, interpreted
in the shipping facility timezone, falls in the selected period.

Numerator:

`SUM(LEAST(cumulative ship-confirmed quantity in base UOM, required quantity))`

Denominator:

`SUM(ordered quantity)`

Policies:

- use base UOM;
- customer cancellation before pick is excluded;
- company cancellation is unfilled;
- an approved substitute counts only through an effective
  `SUBSTITUTES_FOR` item mapping linked to the order line; a silent substitute
  does not;
- returns do not reduce this metric;
- over-shipment is capped at ordered quantity;
- unresolved UOM is excluded and disclosed;
- this is not order-fill, line-fill, or on-time-in-full.

## M4 — Days inventory

Metric id: `DAYS_INVENTORY`

Version: `1.0.0`

Business question:

> For how many days would currently available inventory cover recent demand?

Default grain: facility × item × as-of date.

Available quantity:

`WMS physical on_hand - quality_hold - allocated`

`on_hand` is gross physical quantity and therefore includes held and allocated
stock before the two deductions. ERP book inventory is diagnostic only.

Demand:

trailing 28 complete calendar days ending immediately before the as-of local
date, divided by 28, at the same facility and item. Finished goods use
ship-confirmed customer quantity; components use production issues.

Formula:

`available quantity / average daily demand`

Policies:

- in-transit stock is excluded;
- zero demand returns null and `ZERO_DEMAND`;
- network rollup sums available quantity and demand before division;
- do not average SKU-level days;
- WMS physical and ERP book views are diagnostics, not values to average;
- default inventory class is finished goods and must be shown in scope;
- facility has no hidden default: a missing facility must be clarified, except
  an explicit `NETWORK` scope, which uses the rollup rule above.

## M5 — Landed cost per accepted unit

Metric id: `LANDED_COST_PER_ACCEPTED_UNIT`

Version: `1.0.0`

Business question:

> What known acquisition and inbound logistics cost was incurred for each
> accepted unit?

Components:

- merchandise;
- inbound freight;
- duty;
- insurance;
- brokerage;
- accessorials;
- visible credits/drawbacks.

Economic dates:

- merchandise: commercial invoice date;
- freight: carrier invoice date;
- duty: customs entry date;
- insurance: premium booking date;
- brokerage/accessorial: invoice date.

Allocation:

- freight by chargeable weight, then volume, then merchandise value;
- exhaust that fallback across the freight pool before calling the allocation
  basis missing. A pool is the set of accepted receipts that share one visible
  freight invoice. Use the first basis that is present on every receipt in the
  pool;
- duty and brokerage by customs value;
- insurance by merchandise value;
- a credit attached to one receipt applies to that receipt. No credit record
  means no credit.

Formula, when every accepted quantity in scope is covered:

`SUM(known allocated components in reporting currency) / SUM(accepted quantity)`

Coverage comes from this published rule plus visible source records. Do not
infer a missing document from hidden simulation truth.

Population and clock:

- a receipt is in the reporting period when the local acceptance date at the
  receiving facility falls in that period;
- component economic dates select the FX rate and the component's own
  visibility. They do not move the receipt into another period;
- a component amount, date, currency, or FX rate is visible only when its
  source record's `VISIBLE_AT <= RECORDED_AS_OF`.

What is required:

- Merchandise is required for every accepted receipt. A missing amount, invoice
  date, or economic-date FX rate leaves that accepted quantity uncovered.
- Inbound freight is required only when the visible Incoterm is `EXW` or `FCA`.
  For `DAP` and `DDP`, freight is required only when a visible freight
  obligation exists.
- Duty is required only for a cross-border receipt whose visible Incoterm is
  `EXW`, `FCA`, or `DAP`. Same-country duty is not applicable. `DDP` duty is
  required only when a visible duty obligation says the buyer was charged.
  Unknown duty is never stored as zero. A source-recorded assessed amount of
  zero is valid and is different from a missing amount.
- Brokerage, insurance, and accessorials are required only when that receipt
  has a visible obligation.
- A credit is required only when a visible credit obligation exists. No credit
  record means no credit, not a missing cost.
- V1 supports only `EXW`, `FCA`, `DAP`, and `DDP`. A missing or unsupported
  Incoterm, country, currency, or calendar leaves the affected quantity
  uncovered.

Policies:

- each present component uses the governed FX rate for its economic date, with
  half-even rounding to USD cents;
- rejected quantity cost remains quality loss and is not spread onto accepted
  units;
- late invoices restate a later as-of result. They do not change customer OTD
  unless delivery evidence also changed;
- if any accepted quantity in scope is uncovered, the status is `INCOMPLETE`,
  the canonical value is withheld, and “known cost per covered accepted unit”
  is a labelled diagnostic only;
- the diagnostic uses only covered accepted quantity. It is null when covered
  quantity is zero;
- the answer always displays included quantity / total quantity coverage.

## Operations diagnostics

These counts are not a sixth metric and are not a new formula. They are fields
on the selected SQL answer envelope, counted from the contribution rows that
envelope already contains. Streamlit displays them and does not calculate them.

- Affected commitments: eligible contribution rows whose outcome is a miss.
  When the grain is not an order or schedule line, the interface calls this
  figure affected rows.
- Affected units: the sum of those rows' base-UOM quantities.
- Unresolved records: the envelope's excluded-row count.

## Population clarifications

Recorded before the full-world build. No golden fixture result changed.

- An excluded line belongs to the answer whose period contains its period
  date: the supplier commitment for M1 (the buyer-requested date when no
  calendar exists, because the acknowledgement window cannot be evaluated), the
  original promise for M2. A defective line is not disclosed in every period.
- M1: a missing calendar excludes and discloses the line. It is never dropped
  silently.
- M2: a customer cancellation recorded before pick excludes the line with
  `CUSTOMER_CANCELLED`. A company cancellation remains a miss.
- A source row that carries `VISIBLE_AT` does not exist before that moment. This
  applies to order lines, receipts, and demand rows as well as events.
- M4 `NETWORK`: each facility's 28-day window ends the day before the as-of
  date in that facility's own timezone, then available quantity and demand are
  summed before division.

## Rejected aliases

- Bare “OTD” — must clarify inbound versus outbound.
- “Shipping on time” — not customer delivery.
- “OTIF” — not equivalent to either OTD metric.
- “Fill rate” without unit qualifier — maps to `UNIT_FILL_RATE` only after the
  user explicitly confirms that interpretation.
- “Inventory days” without class — clarify class; without facility/network
  scope — clarify scope.
- “Cost” — insufficient; ask which cost.
- Merchandise plus outbound freight — not landed cost.
- Customer rating — not delivery performance.

## Versioning

Major:

- formula, grain, population, clock, allocation, or edge policy changes.

Minor:

- new governed dimensions or filters that do not change existing results.

Patch:

- documentation or metadata correction without calculation change.

Historical versions remain auditable. Only one version is published as current.

