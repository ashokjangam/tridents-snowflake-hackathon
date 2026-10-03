"""Reference metric functions for contract version 1.0.0.

These functions are the golden oracle. They read already visible canonical
inputs. They do not read hidden simulation truth, and they do not infer a
missing cost document from it.

Streamlit and local preview must not import this module.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from concordia.calendar import add_business_days, calendar_from, local_date, parse_utc
from concordia.contracts import METRIC_VERSION, SUPPORTED_INCOTERMS
from concordia.money import D, allocate_cents, display_str, qty, qty_str, to_usd_cents

PERIOD_INCOTERM_REASONS = frozenset(
    {"INCOTERM_MISSING", "INCOTERM_UNSUPPORTED", "TIMEZONE_MISSING", "CALENDAR_MISSING"}
)


def run_case(case: dict, as_of: str) -> dict:
    moment = parse_utc(as_of)
    metric_id = case["metric_id"]
    if metric_id == "INBOUND_SUPPLIER_OTD":
        result = _inbound(case, moment)
    elif metric_id == "OUTBOUND_CUSTOMER_OTD":
        result = _outbound(case, moment)
    elif metric_id == "UNIT_FILL_RATE":
        result = _fill(case, moment)
    elif metric_id == "DAYS_INVENTORY":
        result = _days(case, moment)
    elif metric_id == "LANDED_COST_PER_ACCEPTED_UNIT":
        result = _landed(case, moment)
    else:
        raise KeyError(metric_id)
    result["metric_id"] = metric_id
    result["metric_version"] = METRIC_VERSION
    result["origin"] = "DERIVED_FROM_SYNTHETIC"
    result["as_of"] = as_of
    return result


def evidence_preimage(result: dict, case: dict) -> dict:
    return {
        "as_of": result["as_of"],
        "denominator": result["denominator"],
        "metric_id": result["metric_id"],
        "metric_version": result["metric_version"],
        "numerator": result["numerator"],
        "origin": result["origin"],
        "period": case["period"],
        "reasons": result["reasons"],
        "scope": case.get("scope") or {},
        "status": result["status"],
    }


def _blank(status: str, reasons: list[str] | None = None, unresolved: int = 0) -> dict:
    return {
        "status": status,
        "numerator": None,
        "denominator": None,
        "value": None,
        "display": None,
        "reasons": sorted(set(reasons or [])),
        "coverage": None,
        "diagnostic_value": None,
        "diagnostic_display": None,
        "excluded_count": unresolved,
        "affected_commitments": 0,
        "affected_units": qty_str(Decimal("0")),
        "unresolved_records": unresolved,
        "evidence_ids": [],
    }


def _ratio_result(
    status: str,
    numerator: Decimal,
    denominator: Decimal,
    *,
    count_ratio: bool,
    reasons: list[str],
    excluded_count: int,
    population: int,
    misses: list[dict],
    evidence_ids: list[str],
) -> dict:
    coverage = None
    if population:
        coverage = qty_str(qty(Decimal(population - excluded_count) / Decimal(population)))
    result = _blank(status, reasons, excluded_count)
    result["evidence_ids"] = evidence_ids
    result["affected_commitments"] = len(misses)
    result["affected_units"] = qty_str(sum((item["qty"] for item in misses), Decimal("0")))
    result["unresolved_records"] = excluded_count
    if status in {"ABSTAIN", "ZERO_DENOMINATOR", "CLARIFY"} or denominator == 0:
        return result
    result["numerator"] = str(int(numerator)) if count_ratio else qty_str(numerator)
    result["denominator"] = str(int(denominator)) if count_ratio else qty_str(denominator)
    value = numerator / denominator
    result["value"] = format(value, "f")
    result["display"] = display_str(value)
    result["coverage"] = coverage if coverage is not None else qty_str(Decimal("1"))
    return result


def _in_period(day: date, period: list[str]) -> bool:
    start, end = date.fromisoformat(period[0]), date.fromisoformat(period[1])
    return start <= day <= end


def _seen(value: str | None, as_of: datetime) -> bool:
    return value is not None and parse_utc(value) <= as_of


def _recorded(row: dict, as_of: datetime) -> bool:
    """A row that carries its own VISIBLE_AT exists only from that moment."""
    return row.get("visible_at") is None or _seen(row["visible_at"], as_of)


def _line_scope(line: dict, scope: dict) -> bool:
    for key in ("supplier_id", "customer_id"):
        if scope.get(key) and line.get(key) != scope[key]:
            return False
    if scope.get("item_id") and line.get("item_id") != scope["item_id"]:
        return False
    if scope.get("facility_id") and line.get("facility_id") != scope["facility_id"]:
        return False
    if scope.get("geography_id") and line.get("geography_id") != scope["geography_id"]:
        return False
    return True


def _exclusion_flags(line: dict) -> list[str]:
    reasons = []
    if line.get("identity_resolved") is False:
        reasons.append("IDENTITY_UNRESOLVED")
    if line.get("uom_resolved") is False:
        reasons.append("UOM_UNRESOLVED")
    if line.get("timezone_resolved") is False or not line.get("timezone"):
        reasons.append("TIMEZONE_MISSING")
    if calendar_from(line.get("calendar")) is None:
        reasons.append("CALENDAR_MISSING")
    if line.get("disposition_missing"):
        reasons.append("DISPOSITION_MISSING")
    return reasons


def _inbound(case: dict, as_of: datetime) -> dict:
    hits = []
    misses = []
    excluded = []
    for line in case["lines"]:
        if not _line_scope(line, case.get("scope", {})) or not _recorded(line, as_of):
            continue
        flags = _exclusion_flags(line)
        if line.get("cancellation") == "BUYER_BEFORE_COMMITMENT":
            flags.append("BUYER_CANCELLED")
        if flags:
            # Period membership still uses the commitment where it can be derived.
            # Without a calendar the acknowledgement window is unknowable, so the
            # buyer-requested date places the excluded line in its period.
            governed = calendar_from(line.get("calendar"))
            if governed is not None:
                commitment = _supplier_commitment(line, governed, as_of)
            else:
                commitment = date.fromisoformat(line["buyer_requested_on"])
            if _in_period(commitment, case["period"]):
                line_qty = qty(line["ordered_qty"]) if line.get("ordered_qty") is not None else Decimal("0")
                excluded.append({"id": line["line_id"], "qty": line_qty, "reasons": flags})
            continue
        governed = calendar_from(line["calendar"])
        commitment = _supplier_commitment(line, governed, as_of)
        if not _in_period(commitment, case["period"]):
            continue
        ordered = qty(line["ordered_qty"])
        as_of_local = local_date(as_of, line["timezone"])
        completed_on = _completion_day(line.get("accepted", []), ordered, as_of)
        if line.get("cancellation") == "SUPPLIER_LATE" and completed_on is None:
            misses.append({"id": line["line_id"], "qty": ordered})
            continue
        if completed_on is None and commitment > as_of_local:
            excluded.append({"id": line["line_id"], "qty": ordered, "reasons": ["FUTURE_OPEN"]})
            continue
        if completed_on is not None and completed_on <= commitment:
            hits.append({"id": line["line_id"], "qty": ordered})
        else:
            misses.append({"id": line["line_id"], "qty": ordered})
    return _finish_count("INBOUND", case, hits, misses, excluded)


def _supplier_commitment(line: dict, governed, as_of: datetime) -> date:
    deadline = add_business_days(date.fromisoformat(line["issued_on"]), 2, governed)
    ack_on = line.get("ack_on")
    usable = False
    if ack_on and line.get("ack_promise_on") and _seen(line.get("ack_visible_at"), as_of):
        acknowledged = date.fromisoformat(ack_on)
        first_receipt = line.get("first_receipt_on")
        after_receipt = first_receipt is not None and acknowledged > date.fromisoformat(first_receipt)
        usable = acknowledged <= deadline and not after_receipt
    if usable:
        return date.fromisoformat(line["ack_promise_on"])
    return date.fromisoformat(line["buyer_requested_on"])


def _completion_day(events: list[dict], required: Decimal, as_of: datetime) -> date | None:
    running = Decimal("0")
    for event in sorted(events, key=lambda item: item["on"]):
        if not _seen(event.get("visible_at"), as_of):
            continue
        running += qty(event["qty"])
        if running >= required:
            return date.fromisoformat(event["on"])
    return None


def _outbound(case: dict, as_of: datetime) -> dict:
    hits = []
    misses = []
    excluded = []
    for line in case["lines"]:
        if not _line_scope(line, case.get("scope", {})) or not _recorded(line, as_of):
            continue
        flags = []
        if line.get("identity_resolved") is False:
            flags.append("IDENTITY_UNRESOLVED")
        if line.get("uom_resolved") is False:
            flags.append("UOM_UNRESOLVED")
        if not line.get("timezone"):
            flags.append("TIMEZONE_MISSING")
        if calendar_from(line.get("calendar")) is None:
            flags.append("CALENDAR_MISSING")
        incoterm = line.get("incoterm")
        if not incoterm:
            flags.append("INCOTERM_MISSING")
        elif incoterm not in SUPPORTED_INCOTERMS:
            flags.append("INCOTERM_UNSUPPORTED")
        ordered = qty(line["ordered_qty"]) if line.get("ordered_qty") is not None else Decimal("0")
        promise = date.fromisoformat(line["original_promise_on"])
        if not _in_period(promise, case["period"]):
            continue
        if flags:
            excluded.append({"id": line["line_id"], "qty": ordered, "reasons": flags})
            continue
        if line.get("cancellation") == "CUSTOMER_BEFORE_PICK":
            excluded.append({"id": line["line_id"], "qty": ordered, "reasons": ["CUSTOMER_CANCELLED"]})
            continue
        if _customer_hold_excludes(line, promise):
            excluded.append({"id": line["line_id"], "qty": ordered, "reasons": ["CUSTOMER_HOLD"]})
            continue
        required = ordered
        short_qty = line.get("short_close_qty")
        if short_qty is not None and line.get("short_close_approved_on"):
            if date.fromisoformat(line["short_close_approved_on"]) <= promise:
                required = qty(short_qty)
        kind = "READY" if incoterm in {"EXW", "FCA"} else "POD"
        counted = [
            event
            for event in line.get("events", [])
            if event.get("kind") == kind
        ]
        completed_on = _completion_day(counted, required, as_of)
        as_of_local = local_date(as_of, line["timezone"])
        row_qty = required
        if completed_on is None and promise > as_of_local:
            excluded.append({"id": line["line_id"], "qty": row_qty, "reasons": ["FUTURE_OPEN"]})
        elif completed_on is not None and completed_on <= promise:
            hits.append({"id": line["line_id"], "qty": row_qty})
        else:
            misses.append({"id": line["line_id"], "qty": row_qty})
    return _finish_count("OUTBOUND", case, hits, misses, excluded)


def _customer_hold_excludes(line: dict, promise: date) -> bool:
    start, end, recorded = line.get("hold_start"), line.get("hold_end"), line.get("hold_recorded_on")
    if not (start and end and recorded):
        return False
    recorded_on = date.fromisoformat(recorded)
    return recorded_on <= promise and date.fromisoformat(start) <= promise <= date.fromisoformat(end)


def _finish_count(kind: str, case: dict, hits: list[dict], misses: list[dict], excluded: list[dict]) -> dict:
    del kind, case
    reasons = [reason for row in excluded for reason in row["reasons"]]
    evidence = sorted(row["id"] for row in hits + misses + excluded)
    eligible = len(hits) + len(misses)
    population = eligible + len(excluded)
    structural = any(reason in PERIOD_INCOTERM_REASONS for reason in reasons)
    if eligible == 0 and structural:
        status = "ABSTAIN"
    elif eligible == 0:
        status = "ZERO_DENOMINATOR"
    elif structural:
        status = "INCOMPLETE"
    else:
        status = "COMPLETE"
    return _ratio_result(
        status,
        Decimal(len(hits)),
        Decimal(eligible),
        count_ratio=True,
        reasons=reasons,
        excluded_count=len(excluded),
        population=population,
        misses=misses,
        evidence_ids=evidence,
    )


def _fill(case: dict, as_of: datetime) -> dict:
    numerator = Decimal("0")
    denominator = Decimal("0")
    excluded = []
    shorts = []
    evidence = []
    reasons: list[str] = []
    included = 0
    for line in case["lines"]:
        if not _line_scope(line, case.get("scope", {})) or not _recorded(line, as_of):
            continue
        requested = date.fromisoformat(line["requested_ship_on"])
        if not _in_period(requested, case["period"]):
            continue
        evidence.append(line["line_id"])
        if line.get("uom_resolved") is False or line.get("ordered_qty") is None:
            excluded.append(line["line_id"])
            reasons.append("UOM_UNRESOLVED")
            continue
        if line.get("cancellation") == "CUSTOMER_BEFORE_PICK":
            excluded.append(line["line_id"])
            reasons.append("CUSTOMER_CANCELLED")
            continue
        ordered = qty(line["ordered_qty"])
        shipped = Decimal("0")
        if line.get("cancellation") != "COMPANY":
            if line.get("substitute") == "SILENT":
                shipped = Decimal("0")
            elif _seen(line.get("ship_visible_at"), as_of):
                shipped = qty(line.get("ship_confirmed_qty", "0"))
        capped = min(shipped, ordered)
        numerator += capped
        denominator += ordered
        included += 1
        if capped < ordered:
            shorts.append({"id": line["line_id"], "qty": ordered})
    status = "COMPLETE" if denominator > 0 else "ZERO_DENOMINATOR"
    return _ratio_result(
        status,
        numerator,
        denominator,
        count_ratio=False,
        reasons=reasons,
        excluded_count=len(excluded),
        population=included + len(excluded),
        misses=shorts,
        evidence_ids=sorted(evidence),
    )


def _days(case: dict, as_of: datetime) -> dict:
    scope = case.get("scope", {})
    if not scope.get("inventory_class"):
        return _blank("CLARIFY", ["INVENTORY_CLASS_MISSING"])
    if not scope.get("network") and not scope.get("facility_id"):
        return _blank("CLARIFY", ["FACILITY_SCOPE_MISSING"])
    zones = case.get("facility_timezones") or {}
    zone = case.get("timezone")
    if not zone and not zones:
        return _blank("ABSTAIN", ["TIMEZONE_MISSING"])

    def window(facility_id: str) -> tuple[date, date] | None:
        facility_zone = zone or zones.get(facility_id)
        if not facility_zone:
            return None
        as_of_local = local_date(as_of, facility_zone)
        return (
            as_of_local.fromordinal(as_of_local.toordinal() - 28),
            as_of_local.fromordinal(as_of_local.toordinal() - 1),
        )

    visible = [
        row
        for row in case.get("snapshots", [])
        if _seen(row.get("visible_at"), as_of) and _snapshot_scope(row, scope)
    ]
    if not visible:
        return _blank("ABSTAIN", ["SNAPSHOT_MISSING"])
    latest_by_facility: dict[str, dict] = {}
    for row in visible:
        facility = row["facility_id"]
        current = latest_by_facility.get(facility)
        if current is None or row["visible_at"] > current["visible_at"]:
            latest_by_facility[facility] = row
    available = Decimal("0")
    for row in latest_by_facility.values():
        facility_available = qty(row["on_hand"]) - qty(row["quality_hold"]) - qty(row["allocated"])
        if facility_available < 0:
            return _blank("ABSTAIN", ["NEGATIVE_AVAILABLE"])
        available += facility_available
    demand = Decimal("0")
    for row in case.get("demand", []):
        if not _snapshot_scope(row, scope) or not _recorded(row, as_of):
            continue
        bounds = window(row["facility_id"])
        if bounds is None:
            return _blank("ABSTAIN", ["TIMEZONE_MISSING"])
        day = date.fromisoformat(row["on"])
        if bounds[0] <= day <= bounds[1]:
            demand += qty(row["qty"])
    result = _blank("COMPLETE")
    result["evidence_ids"] = sorted(row["snapshot_id"] for row in latest_by_facility.values())
    if demand == 0:
        result["status"] = "ZERO_DEMAND"
        result["reasons"] = ["ZERO_DEMAND"]
        return result
    numerator = qty(available * Decimal(28))
    result["numerator"] = qty_str(numerator)
    result["denominator"] = qty_str(demand)
    value = numerator / demand
    result["value"] = format(value, "f")
    result["display"] = display_str(value)
    result["coverage"] = qty_str(Decimal("1"))
    return result


def _snapshot_scope(row: dict, scope: dict) -> bool:
    if scope.get("item_id") and row.get("item_id") != scope["item_id"]:
        return False
    if scope.get("facility_id") and not scope.get("network") and row.get("facility_id") != scope["facility_id"]:
        return False
    if scope.get("inventory_class") and row.get("inventory_class") != scope["inventory_class"]:
        return False
    return True


def _landed(case: dict, as_of: datetime) -> dict:
    period_rows = []
    for receipt in case["receipts"]:
        if not _line_scope(receipt, case.get("scope", {})) or not _recorded(receipt, as_of):
            continue
        accepted_on = date.fromisoformat(receipt["accepted_on"])
        if not _in_period(accepted_on, case["period"]):
            continue
        period_rows.append(receipt)
    recorded = [receipt for receipt in case["receipts"] if _recorded(receipt, as_of)]
    shares = _freight_shares(period_rows, recorded, as_of)
    covered_cents = 0
    covered_qty = Decimal("0")
    total_qty = Decimal("0")
    reasons = []
    evidence = []
    uncovered = 0
    for receipt in period_rows:
        gaps = _receipt_gaps(receipt, as_of, shares)
        accepted = qty(receipt["accepted_qty"])
        total_qty += accepted
        evidence.append(receipt["receipt_id"])
        if gaps:
            uncovered += 1
            reasons.extend(gaps)
            continue
        covered_cents += _receipt_cents(receipt, as_of, shares)
        covered_qty += accepted
    result = _blank("COMPLETE", reasons, uncovered)
    result["evidence_ids"] = sorted(evidence)
    result["unresolved_records"] = uncovered
    if total_qty == 0:
        result["status"] = "ZERO_DENOMINATOR"
        return result
    result["coverage"] = qty_str(qty(covered_qty / total_qty))
    if uncovered:
        result["status"] = "INCOMPLETE"
        result["numerator"] = None
        result["denominator"] = None
        result["value"] = None
        result["display"] = None
        if covered_qty > 0:
            diagnostic = Decimal(covered_cents) / covered_qty / Decimal(100)
            result["diagnostic_value"] = format(diagnostic, "f")
            result["diagnostic_display"] = display_str(diagnostic)
        return result
    value = Decimal(covered_cents) / covered_qty / Decimal(100)
    result["numerator"] = str(covered_cents)
    result["denominator"] = qty_str(covered_qty)
    result["value"] = format(value, "f")
    result["display"] = display_str(value)
    return result


def _components(receipt: dict, kind: str, as_of: datetime) -> list[dict]:
    return [
        component
        for component in receipt.get("components", [])
        if component["kind"] == kind and _seen(component.get("obligation_visible_at"), as_of)
    ]


def _amount_visible(component: dict, as_of: datetime) -> bool:
    return component.get("amount_minor") is not None and _seen(component.get("amount_visible_at"), as_of)


def _converted_amount(component: dict, as_of: datetime) -> tuple[int | None, str | None]:
    if not _amount_visible(component, as_of):
        return None, "AMOUNT_MISSING"
    if component["kind"] == "MERCHANDISE" and not component.get("invoice_date"):
        return None, "INVOICE_DATE_MISSING"
    if component["kind"] != "MERCHANDISE" and not component.get("economic_date"):
        return None, "ECONOMIC_DATE_MISSING"
    if not component.get("currency"):
        return None, "CURRENCY_MISSING"
    if not _seen(component.get("fx_visible_at"), as_of) or component.get("fx_rate") is None:
        return None, "FX_MISSING"
    return to_usd_cents(int(component["amount_minor"]), component["fx_rate"]), None


def _receipt_gaps(receipt: dict, as_of: datetime, shares: dict[str, int | None]) -> list[str]:
    gaps = []
    if not receipt.get("calendar_id"):
        gaps.append("CALENDAR_MISSING")
    incoterm = receipt.get("incoterm")
    if not incoterm:
        gaps.append("INCOTERM_MISSING")
    elif incoterm not in SUPPORTED_INCOTERMS:
        gaps.append("INCOTERM_UNSUPPORTED")
    if not receipt.get("origin_country") or not receipt.get("dest_country"):
        gaps.append("COUNTRY_MISSING")
    merchandise = _components(receipt, "MERCHANDISE", as_of)
    if not merchandise or not _amount_visible(merchandise[0], as_of):
        gaps.append("MERCHANDISE_AMOUNT_MISSING")
    else:
        _append_component_gap(gaps, merchandise[0], as_of, "MERCHANDISE")
    if incoterm in {"EXW", "FCA"}:
        _append_required_freight(gaps, receipt, as_of, shares)
    elif incoterm in {"DAP", "DDP"} and _components(receipt, "FREIGHT", as_of):
        _append_required_freight(gaps, receipt, as_of, shares)
    if incoterm in SUPPORTED_INCOTERMS and receipt.get("origin_country") and receipt.get("dest_country"):
        if _duty_required(receipt, as_of):
            _append_named_gap(gaps, receipt, as_of, "DUTY", shares)
    for kind in ("BROKERAGE", "INSURANCE", "ACCESSORIAL", "CREDIT"):
        if _components(receipt, kind, as_of):
            _append_named_gap(gaps, receipt, as_of, kind, shares)
    return gaps


def _duty_required(receipt: dict, as_of: datetime) -> bool:
    if receipt["origin_country"] == receipt["dest_country"]:
        return False
    incoterm = receipt["incoterm"]
    if incoterm in {"EXW", "FCA", "DAP"}:
        return True
    if incoterm == "DDP":
        return any(component.get("buyer_charged") for component in _components(receipt, "DUTY", as_of))
    return False


def _append_component_gap(gaps: list[str], component: dict, as_of: datetime, prefix: str) -> None:
    _amount, reason = _converted_amount(component, as_of)
    if reason == "AMOUNT_MISSING":
        gaps.append(f"{prefix}_AMOUNT_MISSING")
    elif reason == "INVOICE_DATE_MISSING":
        gaps.append(f"{prefix}_INVOICE_DATE_MISSING")
    elif reason == "ECONOMIC_DATE_MISSING":
        gaps.append(f"{prefix}_ECONOMIC_DATE_MISSING")
    elif reason == "CURRENCY_MISSING":
        gaps.append("CURRENCY_MISSING")
    elif reason == "FX_MISSING":
        gaps.append(f"{prefix}_FX_MISSING")


def _append_required_freight(gaps: list[str], receipt: dict, as_of: datetime, shares: dict[str, int | None]) -> None:
    components = _components(receipt, "FREIGHT", as_of)
    if not components or not _amount_visible(components[0], as_of):
        gaps.append("FREIGHT_AMOUNT_MISSING")
        return
    _append_component_gap(gaps, components[0], as_of, "FREIGHT")
    if shares.get(receipt["receipt_id"]) is None:
        gaps.append("FREIGHT_ALLOCATION_BASIS_MISSING")


def _append_named_gap(gaps: list[str], receipt: dict, as_of: datetime, kind: str, shares: dict[str, int | None]) -> None:
    components = _components(receipt, kind, as_of)
    if not components or not _amount_visible(components[0], as_of):
        gaps.append(f"{kind}_AMOUNT_MISSING")
        return
    _append_component_gap(gaps, components[0], as_of, kind)
    if kind in {"DUTY", "BROKERAGE"} and components[0].get("customs_value_minor") is None:
        gaps.append(f"{kind}_ALLOCATION_BASIS_MISSING")
    if kind == "INSURANCE" and components[0].get("merchandise_value_minor") is None and not _components(receipt, "MERCHANDISE", as_of):
        gaps.append("INSURANCE_ALLOCATION_BASIS_MISSING")
    if kind == "FREIGHT" and shares.get(receipt["receipt_id"]) is None:
        gaps.append("FREIGHT_ALLOCATION_BASIS_MISSING")


def _freight_shares(period_rows: list[dict], all_receipts: list[dict], as_of: datetime) -> dict[str, int | None]:
    pools: dict[str, list[dict]] = {}
    for receipt in all_receipts:
        for component in _components(receipt, "FREIGHT", as_of):
            if not _amount_visible(component, as_of):
                continue
            pool_id = component.get("allocation_pool_id") or receipt["receipt_id"]
            pools.setdefault(pool_id, [])
            if receipt not in pools[pool_id]:
                pools[pool_id].append(receipt)
    shares: dict[str, int | None] = {}
    for pool_id, members in pools.items():
        amounts = []
        for member in members:
            for component in _components(member, "FREIGHT", as_of):
                if (component.get("allocation_pool_id") or member["receipt_id"]) == pool_id and _amount_visible(component, as_of):
                    amounts.append(int(component["amount_minor"]))
        if len(set(amounts)) != 1:
            for member in members:
                shares[member["receipt_id"]] = None
            continue
        total = amounts[0]
        basis = _pool_basis(members, as_of)
        if basis is None:
            for member in members:
                shares[member["receipt_id"]] = None
            continue
        weights = [item[1] for item in basis]
        allocated = allocate_cents(to_usd_cents(total, _fx_of(members[0], "FREIGHT", as_of)), weights)
        for (member, _weight), share in zip(basis, allocated):
            shares[member["receipt_id"]] = shares.get(member["receipt_id"], 0) + share if shares.get(member["receipt_id"]) is not None else share
    for receipt in period_rows:
        shares.setdefault(receipt["receipt_id"], None)
    return shares


def _fx_of(receipt: dict, kind: str, as_of: datetime) -> str:
    component = _components(receipt, kind, as_of)[0]
    return str(component["fx_rate"])


def _pool_basis(members: list[dict], as_of: datetime) -> list[tuple[dict, Decimal]] | None:
    weight = _weights(members, as_of, "chargeable_weight")
    if weight is not None:
        return weight
    volume = _weights(members, as_of, "volume")
    if volume is not None:
        return volume
    values = []
    for member in members:
        merchandise = _components(member, "MERCHANDISE", as_of)
        if not merchandise or not _amount_visible(merchandise[0], as_of):
            return None
        amount, reason = _converted_amount(merchandise[0], as_of)
        if reason or amount is None:
            return None
        values.append((member, Decimal(amount)))
    if sum((item[1] for item in values), Decimal("0")) <= 0:
        return None
    return values


def _weights(members: list[dict], as_of: datetime, field: str) -> list[tuple[dict, Decimal]] | None:
    rows = []
    for member in members:
        component = _components(member, "FREIGHT", as_of)
        if not component or component[0].get(field) is None:
            return None
        rows.append((member, D(component[0][field])))
    if sum((item[1] for item in rows), Decimal("0")) <= 0:
        return None
    return rows


def _receipt_cents(receipt: dict, as_of: datetime, shares: dict[str, int | None]) -> int:
    total = 0
    for kind in ("MERCHANDISE", "DUTY", "INSURANCE", "BROKERAGE", "ACCESSORIAL"):
        if kind == "DUTY" and not _duty_required(receipt, as_of):
            continue
        for component in _components(receipt, kind, as_of):
            if _amount_visible(component, as_of):
                amount, reason = _converted_amount(component, as_of)
                if reason is None and amount is not None:
                    total += amount
    freight = shares.get(receipt["receipt_id"])
    if freight is not None and _components(receipt, "FREIGHT", as_of):
        total += freight
    for component in _components(receipt, "CREDIT", as_of):
        if _amount_visible(component, as_of):
            amount, reason = _converted_amount(component, as_of)
            if reason is None and amount is not None:
                total -= amount
    return total
