"""Daily state machine for Meridian Motion, CONCORDIA_SIM_V1.

Truth only. Source projections, distortions and delays are added in
`sim.project`. Product code never reads this module's output directly.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from concordia.seed import stream_generator
from sim.master import FACILITY_CALENDAR, PLANT_DC, SERVING, build_master, facility, geography
from sim.world import FACILITIES

START = date(2025, 1, 1)
ORDER_END = date(2026, 6, 30)
END = date(2026, 7, 15)
UTC = timezone.utc

HERO_MONTH = (date(2026, 5, 1), date(2026, 5, 31))
HERO_PO_FREEZE = (date(2026, 4, 6), date(2026, 6, 5))
HERO_RESERVE_ON = date(2026, 5, 6)
DAYTON_SHUTDOWN = {date(2026, 5, 25)}


def utc_at(day: date, hour: float, zone: str) -> datetime:
    whole = int(hour)
    minute = int(round((hour - whole) * 60))
    if minute == 60:
        whole, minute = whole + 1, 0
    local = datetime(day.year, day.month, day.day, min(whole, 23), minute, tzinfo=ZoneInfo(zone))
    return local.astimezone(UTC)


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_business(day: date, facility_id: str | None = None) -> bool:
    if day.weekday() >= 5:
        return False
    if facility_id and FACILITY_CALENDAR.get(facility_id) == "CAL-DAYTON" and day in DAYTON_SHUTDOWN:
        return False
    return True


def next_business(day: date, facility_id: str | None = None) -> date:
    while not is_business(day, facility_id):
        day += timedelta(days=1)
    return day


def add_business(day: date, count: int, facility_id: str | None = None) -> date:
    while count > 0:
        day += timedelta(days=1)
        if is_business(day, facility_id):
            count -= 1
    return day


def in_hero_month(day: date | None) -> bool:
    return day is not None and HERO_MONTH[0] <= day <= HERO_MONTH[1]


class World:
    def __init__(self) -> None:
        self.rng = {name: stream_generator(name) for name in (
            "demand", "supply", "production", "quality", "transit", "commercial", "feedback", "defects")}
        self.master = build_master(self.rng["supply"])
        self.items = self.master["items_by_id"]
        self.suppliers = {row["supplier_id"]: row for row in self.master["suppliers"]}
        self.supplier_of = {row["item_id"]: row["supplier_id"] for row in self.master["supply"]}
        self.customers = {row["customer_id"]: row for row in self.master["customers"]}
        self.on_hand = defaultdict(int)
        self.holds: dict[tuple, list[dict]] = defaultdict(list)
        self.allocated = defaultdict(int)
        self.in_transit = defaultdict(int)
        self.on_order = defaultdict(int)
        self.pending = defaultdict(int)
        self.po_lines: list[dict] = []
        self.receipts: list[dict] = []
        self.dispositions: list[dict] = []
        self.production: list[dict] = []
        self.issues: list[dict] = []
        self.so_lines: list[dict] = []
        self.shipments: list[dict] = []
        self.deliveries: list[dict] = []
        self.transfers: list[dict] = []
        self.snapshots: list[dict] = []
        self.ratings: list[dict] = []
        self.returns: list[dict] = []
        self.fx: list[dict] = []
        self.costs: list[dict] = []
        self.freight_pools: dict[str, dict] = {}
        self.arrivals: dict[date, list] = defaultdict(list)
        self.completions: dict[date, list] = defaultdict(list)
        self.transfer_arrivals: dict[date, list] = defaultdict(list)
        self.counter = defaultdict(int)
        self._plan_rates()

    def next_id(self, prefix: str) -> str:
        self.counter[prefix] += 1
        return f"{prefix}-{self.counter[prefix]:06d}"

    # ----- planning parameters -------------------------------------------------
    def _plan_rates(self) -> None:
        self.serving_of: dict[tuple[str, str], str] = {}
        weekly = defaultdict(float)
        for customer in self.customers.values():
            for item_id in customer["items"]:
                home = self.items[item_id]["home_facility_id"]
                plant, dc = SERVING[customer["geography_id"]]
                serving = home if home == plant else dc
                self.serving_of[(customer["customer_id"], item_id)] = serving
                weekly[(item_id, serving)] += customer["weekly_rate"] * 9.0
        self.fg_weekly = dict(weekly)
        self.plant_weekly = defaultdict(float)
        for (item_id, serving), rate in weekly.items():
            self.plant_weekly[(item_id, self.items[item_id]["home_facility_id"])] += rate
        # Planning rates use every BOM revision, so both sides of an effectivity switch stay stocked.
        rows_of = defaultdict(dict)
        for row in self.master["bom"]:
            current = rows_of[row["parent_id"]].get(row["component_id"], 0)
            rows_of[row["parent_id"]][row["component_id"]] = max(current, row["qty_per"])
        self.component_weekly = defaultdict(float)
        for (parent, plant), rate in list(self.plant_weekly.items()):
            for component_id, per in rows_of.get(parent, {}).items():
                self.component_weekly[(component_id, plant)] += rate * per
                for sub_id, sub_per in rows_of.get(component_id, {}).items():
                    self.component_weekly[(sub_id, plant)] += rate * per * sub_per

    def _bom(self, parent: str, day: date) -> list[dict]:
        out = []
        for row in self.master["bom"]:
            if row["parent_id"] != parent:
                continue
            start = date.fromisoformat(row["effective_from"])
            end = date.fromisoformat(row["effective_to"]) if row["effective_to"] else None
            if start <= day and (end is None or day < end):
                out.append(row)
        return out

    # ----- inventory helpers ---------------------------------------------------
    def held(self, key) -> int:
        return sum(hold["qty"] for hold in self.holds[key])

    def free(self, key) -> int:
        return self.on_hand[key] - self.held(key) - self.allocated[key]

    def add_hold(self, key, qty: int, release: date, party: str, ref: str) -> None:
        qty = min(qty, max(0, self.on_hand[key] - self.held(key)))
        if qty > 0:
            self.holds[key].append({"qty": qty, "release": release, "party": party, "ref": ref})

    # ----- FX -------------------------------------------------------------------
    def build_fx(self) -> None:
        rng = self.rng["commercial"]
        level = {"EUR": 1.08, "MXN": 0.058, "CNY": 0.139}
        day = START - timedelta(days=10)
        stale = {date(2026, 5, 29), date(2026, 3, 13), date(2025, 11, 7)}
        while day <= END:
            for currency, base in (("EUR", 1.08), ("MXN", 0.058), ("CNY", 0.139)):
                step = float(rng.normal(0, 0.004))
                level[currency] = min(base * 1.12, max(base * 0.88, level[currency] * (1 + step)))
                publish = utc_at(day + timedelta(days=1), 1, "UTC")
                if day in stale:
                    publish = utc_at(day + timedelta(days=9), 1, "UTC")
                self.fx.append({"currency": currency, "rate_date": day.isoformat(), "usd_per_unit": f"{level[currency]:.6f}", "visible_at": iso(publish)})
            day += timedelta(days=1)

    # ----- purchasing ------------------------------------------------------------
    def lead_days(self, supplier: dict) -> int:
        rng = self.rng["supply"]
        mu = {"DOMESTIC": 6, "NEARSHORE": 11, "OVERSEAS": 30}[supplier["tier"]]
        return max(2, int(round(rng.lognormal(mean=0, sigma=0.25) * mu)))

    def issue_po(self, day: date, item_id: str, plant: str, qty: int, *, hero: dict | None = None) -> dict:
        supplier = self.suppliers[self.supplier_of[item_id]]
        rng = self.rng["supply"]
        line_id = hero["line_id"] if hero else self.next_id("PO")
        lead = self.lead_days(supplier)
        requested = next_business(day + timedelta(days=lead), plant)
        line = {
            "line_id": line_id, "supplier_id": supplier["supplier_id"], "item_id": item_id, "facility_id": plant,
            "ordered_qty": qty, "issued_on": day, "buyer_requested_on": requested, "ack": None,
            "cancellation": None, "receipts": [], "incoterm": self.receipt_incoterm(supplier, plant),
            "hero": bool(hero),
        }
        if hero:
            line.update(hero["fields"])
            self.po_lines.append(line)
            return line
        roll = float(rng.random())
        if roll < 0.80:
            ack_on = add_business(day, int(rng.integers(0, 3)), plant)
            line["ack"] = {"ack_on": ack_on, "promise_on": requested + timedelta(days=int(rng.integers(-1, 3))), "visible_at": utc_at(ack_on, 11 + float(rng.uniform(0, 6)), facility(plant)["timezone"])}
        elif roll < 0.92:
            ack_on = add_business(day, int(rng.integers(3, 6)), plant)
            line["ack"] = {"ack_on": ack_on, "promise_on": requested + timedelta(days=int(rng.integers(2, 8))), "visible_at": utc_at(ack_on, 14, facility(plant)["timezone"])}
        if float(rng.random()) < 0.005:
            line["cancellation"] = "BUYER_BEFORE_COMMITMENT"
            self.po_lines.append(line)
            return line
        reliability = supplier["reliability"]
        if supplier["country"] == "MX" and date(2026, 2, 1) <= day <= date(2026, 4, 15):
            reliability -= 0.35
        target = line["ack"]["promise_on"] if line["ack"] and line["ack"]["ack_on"] <= add_business(day, 2, plant) else requested
        if float(rng.random()) < reliability:
            arrive = target - timedelta(days=int(rng.integers(0, 3)))
        else:
            arrive = target + timedelta(days=int(rng.integers(1, 9)))
        arrive = max(next_business(arrive, plant), day + timedelta(days=1))
        if float(rng.random()) < 0.003:
            line["cancellation"] = "SUPPLIER_LATE"
            self.po_lines.append(line)
            return line
        parts = [qty]
        if float(rng.random()) < 0.12 and qty >= 4:
            first = int(qty * float(rng.uniform(0.3, 0.7)))
            parts = [first, qty - first]
        for index, part in enumerate(parts):
            when = arrive if index == 0 else next_business(arrive + timedelta(days=int(rng.integers(2, 8))), plant)
            self.arrivals[when].append({"line": line, "qty": part})
        self.on_order[(item_id, plant)] += qty
        self.po_lines.append(line)
        return line

    def receipt_incoterm(self, supplier: dict, plant: str) -> str:
        if supplier["supplier_id"] == "SUP-001":
            return "EXW"
        country = facility(plant)["country"]
        if supplier["country"] == country:
            return ("EXW", "FCA", "DAP")[int(supplier["supplier_id"][-2:]) % 3]
        if supplier["tier"] == "NEARSHORE":
            return ("FCA", "DAP")[int(supplier["supplier_id"][-2:]) % 2]
        return ("EXW", "FCA", "DDP")[int(supplier["supplier_id"][-2:]) % 3]

    def receive(self, day: date, arrival: dict) -> None:
        line, qty = arrival["line"], arrival["qty"]
        plant, item_id = line["facility_id"], line["item_id"]
        key = (item_id, plant)
        rng = self.rng["quality"]
        tz = facility(plant)["timezone"]
        receipt_id = arrival.get("receipt_id") or self.next_id("GR")
        received_at = utc_at(day, 9 + float(rng.uniform(0, 7)), tz)
        receipt = {"receipt_id": receipt_id, "line_id": line["line_id"], "item_id": item_id, "facility_id": plant,
                   "received_on": day, "qty": qty, "visible_at": received_at + timedelta(hours=float(rng.uniform(0.5, 6))),
                   "supplier_id": line["supplier_id"], "incoterm": line["incoterm"]}
        if arrival.get("visible"):
            receipt["visible_at"] = arrival["visible"]
        self.receipts.append(receipt)
        line["receipts"].append(receipt)
        self.on_order[key] -= qty
        forced = arrival.get("disposition")
        roll = float(rng.random())
        if forced:
            dispositions = forced
        elif roll < 0.04:
            reject = max(1, int(qty * float(rng.uniform(0.05, 0.35))))
            dispositions = [("ACCEPT", qty - reject, day), ("SUPPLIER_REJECT", reject, day)]
        elif roll < 0.07:
            release = add_business(day, int(rng.integers(2, 7)), plant)
            dispositions = [("SUPPLIER_HOLD", qty, day), ("RELEASE", qty, release)]
        else:
            dispositions = [("ACCEPT", qty, day)]
        accepted_qty = 0
        accepted_on = None
        for kind, amount, when in dispositions:
            event = {"receipt_id": receipt_id, "line_id": line["line_id"], "item_id": item_id, "facility_id": plant,
                     "kind": kind, "qty": amount, "on": when, "party": "SUPPLIER" if kind != "PLANT_HOLD" else "PLANT",
                     "visible_at": utc_at(when, 16 + float(rng.uniform(0, 3)), tz)}
            self.dispositions.append(event)
            if kind in ("ACCEPT", "RELEASE") and amount > 0:
                accepted_qty += amount
                accepted_on = accepted_on or when
                event["accepts"] = True
        receipt["accepted_qty"] = accepted_qty
        receipt["accepted_on"] = accepted_on
        receipt["accepted_visible_at"] = max((d["visible_at"] for d in self.dispositions[-len(dispositions):] if d.get("accepts")), default=None)
        rejected = sum(amount for kind, amount, _ in dispositions if kind == "SUPPLIER_REJECT")
        line["supplier_rejected_qty"] = line.get("supplier_rejected_qty", 0) + rejected
        self.on_hand[key] += qty - rejected
        for kind, amount, when in dispositions:
            if kind == "SUPPLIER_HOLD":
                self.add_hold(key, amount, next((w for k, _, w in dispositions if k == "RELEASE"), END), "SUPPLIER", receipt_id)
        plant_hold = arrival.get("plant_hold")
        if plant_hold:
            amount, start, release = plant_hold
            self.dispositions.append({"receipt_id": receipt_id, "line_id": line["line_id"], "item_id": item_id, "facility_id": plant,
                                      "kind": "PLANT_HOLD", "qty": amount, "on": start, "party": "PLANT",
                                      "visible_at": utc_at(start, 15, tz), "release_on": release})
            self.add_hold(key, amount, release, "PLANT", receipt_id)
        elif not forced and float(rng.random()) < 0.02 and accepted_qty > 0:
            start = add_business(day, 1, plant)
            release = add_business(start, int(rng.integers(2, 6)), plant)
            amount = max(1, accepted_qty // 3)
            self.dispositions.append({"receipt_id": receipt_id, "line_id": line["line_id"], "item_id": item_id, "facility_id": plant,
                                      "kind": "PLANT_HOLD", "qty": amount, "on": start, "party": "PLANT",
                                      "visible_at": utc_at(start, 15, tz), "release_on": release})
            self.add_hold(key, amount, release, "PLANT", receipt_id)
        if accepted_qty > 0 and not arrival.get("skip_costs"):
            self.book_costs(receipt, line)

    # ----- landed cost documents -----------------------------------------------------
    def book_costs(self, receipt: dict, line: dict) -> None:
        rng = self.rng["commercial"]
        supplier = self.suppliers[line["supplier_id"]]
        plant = receipt["facility_id"]
        dest = facility(plant)["country"]
        currency = supplier["currency"]
        item = self.items[receipt["item_id"]]
        usd_price = item["price_usd_cents"] if item["item_id"] != "MM-440" else 1000
        rate = {"USD": 1.0, "EUR": 1.08, "MXN": 0.058, "CNY": 0.139}[currency]
        unit_minor = max(1, int(round(usd_price / rate)))
        merch_minor = unit_minor * receipt["accepted_qty"]
        accepted_on = receipt["accepted_on"]
        tz = facility(plant)["timezone"]
        inv_day = accepted_on + timedelta(days=int(rng.integers(0, 3)))
        merch_visible = utc_at(inv_day, 12, tz) + timedelta(days=float(rng.uniform(0.2, 6)))
        if float(rng.random()) < 0.02:
            merch_visible += timedelta(days=float(rng.uniform(20, 60)))
        receipt_id = receipt["receipt_id"]
        self.costs.append({"receipt_id": receipt_id, "kind": "MERCHANDISE", "document_id": self.next_id("INV"),
                           "obligation_visible_at": merch_visible, "amount_minor": merch_minor, "amount_visible_at": merch_visible,
                           "currency": currency, "invoice_date": inv_day, "economic_date": inv_day})
        incoterm = line["incoterm"]
        cross = supplier["country"] != dest
        if incoterm in ("EXW", "FCA"):
            week = accepted_on - timedelta(days=accepted_on.weekday())
            pool_id = f"FRT-{supplier['country']}-{plant[4:7]}-{week.strftime('%y%m%d')}"
            pool = self.freight_pools.setdefault(pool_id, {"pool_id": pool_id, "members": [], "lane": f"LN-{supplier['country']}-{plant}",
                                                            "currency": "USD" if dest == "US" else "EUR", "week": week})
            weight = round(item["unit_weight_kg"] * receipt["accepted_qty"], 2)
            pool["members"].append({"receipt_id": receipt_id, "chargeable_weight": weight if float(rng.random()) > 0.03 else None,
                                    "volume": round(weight / 180, 4)})
        if cross and incoterm in ("EXW", "FCA", "DAP"):
            entry_day = accepted_on - timedelta(days=int(rng.integers(0, 3)))
            visible = utc_at(entry_day, 13, tz) + timedelta(days=float(rng.uniform(2, 16)))
            duty_rate = 0.0 if supplier["country"] == "MX" and dest == "US" else 0.035
            duty_minor_usd = int(round(merch_minor * rate * duty_rate))
            missing = float(rng.random()) < 0.03
            self.costs.append({"receipt_id": receipt_id, "kind": "DUTY", "document_id": self.next_id("CE"),
                               "obligation_visible_at": utc_at(entry_day, 13, tz) + timedelta(days=1),
                               "amount_minor": None if missing else duty_minor_usd, "amount_visible_at": None if missing else visible,
                               "currency": "USD" if dest == "US" else "EUR", "economic_date": entry_day,
                               "customs_value_minor": int(round(merch_minor * rate))})
            self.costs.append({"receipt_id": receipt_id, "kind": "BROKERAGE", "document_id": self.next_id("BRK"),
                               "obligation_visible_at": utc_at(entry_day, 13, tz) + timedelta(days=1),
                               "amount_minor": int(rng.integers(4500, 16000)), "amount_visible_at": visible + timedelta(days=float(rng.uniform(1, 25))),
                               "currency": "USD" if dest == "US" else "EUR", "economic_date": entry_day,
                               "customs_value_minor": int(round(merch_minor * rate))})
        if incoterm == "DDP" and float(rng.random()) < 0.15:
            entry_day = accepted_on
            self.costs.append({"receipt_id": receipt_id, "kind": "DUTY", "document_id": self.next_id("CE"),
                               "obligation_visible_at": utc_at(entry_day, 13, tz), "amount_minor": int(round(merch_minor * rate * 0.02)),
                               "amount_visible_at": utc_at(entry_day, 13, tz) + timedelta(days=4), "currency": "USD" if dest == "US" else "EUR",
                               "economic_date": entry_day, "customs_value_minor": int(round(merch_minor * rate)), "buyer_charged": True})
        if supplier["tier"] == "OVERSEAS" and float(rng.random()) < 0.25:
            self.costs.append({"receipt_id": receipt_id, "kind": "INSURANCE", "document_id": self.next_id("INS"),
                               "obligation_visible_at": merch_visible, "amount_minor": max(100, merch_minor // 200), "amount_visible_at": merch_visible + timedelta(days=3),
                               "currency": currency, "economic_date": inv_day, "merchandise_value_minor": merch_minor})
        if float(rng.random()) < 0.01:
            credit_day = accepted_on + timedelta(days=int(rng.integers(5, 20)))
            self.costs.append({"receipt_id": receipt_id, "kind": "CREDIT", "document_id": self.next_id("CRN"),
                               "obligation_visible_at": utc_at(credit_day, 12, tz), "amount_minor": max(100, merch_minor // 20),
                               "amount_visible_at": utc_at(credit_day, 12, tz) + timedelta(days=2), "currency": currency, "economic_date": credit_day})

    def close_freight_pools(self) -> None:
        rng = self.rng["commercial"]
        for pool in self.freight_pools.values():
            if pool.get("hero"):
                continue
            weight = sum((member["chargeable_weight"] or 0) for member in pool["members"])
            amount = int(round(18000 + weight * float(rng.uniform(55, 95))))
            invoice_day = pool["week"] + timedelta(days=int(rng.integers(7, 16)))
            obligation = utc_at(pool["week"] + timedelta(days=4), 18, "UTC")
            visible = utc_at(invoice_day, 15, "UTC") + timedelta(days=float(rng.lognormal(mean=2.3, sigma=0.6)))
            pool.update({"amount_minor": amount, "invoice_date": invoice_day, "obligation_visible_at": obligation, "amount_visible_at": visible})

    # ----- production -------------------------------------------------------------
    def plan_production(self, day: date) -> None:
        rng = self.rng["production"]
        for (item_id, plant), weekly in sorted(self.plant_weekly.items()):
            item = self.items[item_id]
            if item["purchased"]:
                continue
            self._produce(day, item_id, plant, weekly, rng)
        for item in self.master["items"]:
            if item["item_type"] != "SUBASSEMBLY":
                continue
            plant = item["home_facility_id"]
            weekly = self.component_weekly.get((item["item_id"], plant), 0.0)
            if weekly > 0:
                self._produce(day, item["item_id"], plant, weekly, rng)

    def _produce(self, day: date, item_id: str, plant: str, weekly: float, rng) -> None:
        key = (item_id, plant)
        dc_need = sum(self.fg_weekly.get((item_id, dc), 0.0) for dc in PLANT_DC.values())
        target = int(3.0 * weekly + 2.5 * dc_need) + 8
        position = self.on_hand[key] - self.held(key) - self.allocated[key] + self.pending[key]
        qty = target - position
        if qty <= 0:
            return
        qty = int((qty + 9) // 10 * 10)
        bom = self._bom(item_id, day)
        for row in bom:
            ckey = (row["component_id"], plant)
            available = self.on_hand[ckey] - self.held(ckey) - self.allocated[ckey]
            qty = min(qty, max(0, available) // row["qty_per"])
        if qty <= 0:
            return
        order_id = self.next_id("MO")
        start = day
        complete = add_business(start, int(rng.integers(2, 5)), plant)
        tz = facility(plant)["timezone"]
        for row in bom:
            ckey = (row["component_id"], plant)
            used = qty * row["qty_per"]
            self.on_hand[ckey] -= used
            self.issues.append({"issue_id": self.next_id("ISS"), "order_id": order_id, "component_id": row["component_id"], "facility_id": plant,
                                "qty": used, "on": start, "visible_at": utc_at(start, 20, tz) + timedelta(hours=float(rng.uniform(1, 30))), "revision": row["revision"]})
        order = {"order_id": order_id, "item_id": item_id, "facility_id": plant, "qty": qty, "start_on": start, "complete_on": complete}
        self.production.append(order)
        self.pending[key] += qty
        self.completions[complete].append(order)

    def complete(self, day: date, order: dict) -> None:
        key = (order["item_id"], order["facility_id"])
        self.on_hand[key] += order["qty"]
        self.pending[key] -= order["qty"]
        rng = self.rng["quality"]
        if float(rng.random()) < 0.03:
            release = add_business(day, int(rng.integers(2, 7)), order["facility_id"])
            amount = max(1, order["qty"] // 2)
            order["plant_hold"] = {"qty": amount, "start_on": day, "release_on": release}
            self.add_hold(key, amount, release, "PLANT", order["order_id"])

    def plan_purchasing(self, day: date) -> None:
        for (item_id, plant), weekly in sorted(self.component_weekly.items()):
            if not item_id.startswith("CP-"):
                continue
            key = (item_id, plant)
            supplier = self.suppliers[self.supplier_of[item_id]]
            cover = {"DOMESTIC": 3.0, "NEARSHORE": 4.0, "OVERSEAS": 7.0}[supplier["tier"]]
            position = self.on_hand[key] - self.held(key) + self.on_order[key]
            target = int(weekly * (cover + 3)) + 15
            if position < weekly * (cover + 1) + 8:
                qty = int((target - position + 9) // 10 * 10)
                if qty > 0:
                    self.issue_po(day, item_id, plant, qty)
        # MM-440 is purchased finished goods from Apex at Dayton.
        if not (HERO_PO_FREEZE[0] <= day <= HERO_PO_FREEZE[1]):
            key = ("MM-440", "FAC-DAYTON")
            weekly = self.plant_weekly.get(key, 10.0)
            dc_need = sum(self.fg_weekly.get(("MM-440", dc), 0.0) for dc in PLANT_DC.values())
            position = self.on_hand[key] - self.held(key) - self.allocated[key] + self.on_order[key]
            target = int(3.0 * weekly + 2.5 * dc_need) + 20
            if position < target:
                self.issue_po(day, "MM-440", "FAC-DAYTON", int((target - position + 9) // 10 * 10))

    # ----- distribution centre replenishment ---------------------------------------------
    def replenish(self, day: date) -> None:
        rng = self.rng["transit"]
        for (item_id, serving), weekly in sorted(self.fg_weekly.items()):
            if not serving.startswith("DC-"):
                continue
            home = self.items[item_id]["home_facility_id"]
            key = (item_id, serving)
            same_country = facility(home)["country"] == facility(serving)["country"]
            position = self.on_hand[key] + self.in_transit[key] - self.allocated[key]
            target = int(weekly * (2.0 + (0.4 if same_country else 2.2))) + 6
            need = target - position
            if need <= 0:
                continue
            source = (item_id, home)
            send = min(need, max(0, self.free(source)))
            if send <= 0:
                continue
            transit = max(1, int(round(rng.lognormal(mean=0, sigma=0.2) * (2 if same_country else 14))))
            arrive = day + timedelta(days=transit)
            self.on_hand[source] -= send
            self.in_transit[key] += send
            transfer = {"transfer_id": self.next_id("TR"), "item_id": item_id, "from_id": home, "to_id": serving, "qty": send,
                        "ship_on": day, "arrive_on": arrive, "visible_at": utc_at(day, 21, facility(home)["timezone"])}
            self.transfers.append(transfer)
            self.transfer_arrivals[arrive].append(transfer)

    # ----- sales ----------------------------------------------------------------------
    def create_orders(self, day: date) -> None:
        if day > ORDER_END or not is_business(day):
            return
        rng = self.rng["demand"]
        for customer in self.customers.values():
            if float(rng.random()) > customer["weekly_rate"]:
                continue
            ship_to = customer["ship_tos"][int(rng.integers(0, len(customer["ship_tos"])))]
            lines = 1 + int(rng.negative_binomial(1, 0.55))
            picks = rng.choice(len(customer["items"]), size=min(lines, len(customer["items"])), replace=False)
            order_no = self.next_id("SO")
            for position, pick in enumerate(sorted(int(p) for p in picks)):
                item_id = customer["items"][pick]
                qty = 1 + int(rng.negative_binomial(2, 0.22))
                serving = self.serving_of[(customer["customer_id"], item_id)]
                lead = int(rng.integers(3, 12))
                requested = add_business(day, lead, serving)
                incoterm = str(rng.choice(["DAP", "DAP", "DAP", "DAP", "DAP", "DAP", "DDP", "EXW", "FCA", "DAP"]))
                transit = self.transit_estimate(serving, ship_to["geography_id"])
                if incoterm in ("EXW", "FCA"):
                    promise = requested
                else:
                    promise = add_business(requested, transit + 1, None)
                if item_id == "MM-440" and (in_hero_month(requested) or in_hero_month(promise)):
                    continue
                self.add_so_line(day, order_no, position, customer, ship_to, item_id, qty, serving, requested, promise, incoterm)

    def transit_estimate(self, serving: str, geography_id: str) -> int:
        same = facility(serving)["country"] == geography(geography_id)["country"] or {facility(serving)["country"], geography(geography_id)["country"]} <= {"DE", "NL"}
        return 2 if same else 9

    def add_so_line(self, day, order_no, position, customer, ship_to, item_id, qty, serving, requested, promise, incoterm, hero=None) -> dict:
        rng = self.rng["commercial"]
        line = {
            "line_id": hero["line_id"] if hero else f"{order_no}-{(position + 1) * 10}", "order_id": order_no,
            "customer_id": customer["customer_id"], "ship_to_id": ship_to["ship_to_id"], "geography_id": ship_to["geography_id"],
            "item_id": item_id, "facility_id": serving, "ordered_qty": qty, "required_qty": qty, "order_on": day,
            "requested_ship_on": requested, "original_promise_on": promise, "incoterm": incoterm,
            "shipped": 0, "alloc": 0, "revisions": [], "cancellation": None, "short_close": None, "hold": None,
            "status": "OPEN", "hero": bool(hero), "deliveries": [],
        }
        if hero:
            line.update(hero["fields"])
            self.so_lines.append(line)
            return line
        roll = float(rng.random())
        if roll < 0.01:
            line["cancellation"] = "CUSTOMER_BEFORE_PICK"
            line["cancel_on"] = max(day, requested - timedelta(days=int(rng.integers(1, 3))))
        elif roll < 0.015:
            line["cancellation"] = "COMPANY"
        elif roll < 0.025 and qty >= 3:
            approved = promise - timedelta(days=int(rng.integers(2, 5)))
            if approved > day:
                line["short_close"] = {"qty": max(1, int(qty * float(rng.uniform(0.5, 0.85)))), "approved_on": approved}
                line["required_qty"] = line["short_close"]["qty"]
        elif roll < 0.035:
            start = requested - timedelta(days=1)
            end = promise + timedelta(days=int(rng.integers(2, 6)))
            recorded = max(day, start - timedelta(days=int(rng.integers(1, 4))))
            if recorded <= promise:
                line["hold"] = {"start": start, "end": end, "recorded_on": recorded}
        if float(rng.random()) < 0.08:
            recorded = day + timedelta(days=int(rng.integers(1, max(2, (promise - day).days))))
            if recorded < promise:
                line["revisions"].append({"promise_on": promise + timedelta(days=int(rng.integers(3, 12))), "recorded_on": recorded})
        if float(rng.random()) < 0.005:
            line["silent_substitute"] = True
        self.so_lines.append(line)
        return line

    def ship(self, day: date) -> None:
        open_lines = [line for line in self.so_lines if line["status"] == "OPEN" and not line.get("scripted")]
        open_lines.sort(key=lambda line: (line["requested_ship_on"], line["line_id"]))
        for line in open_lines:
            key = (line["item_id"], line["facility_id"])
            if line["cancellation"] == "CUSTOMER_BEFORE_PICK" and day >= line["cancel_on"]:
                self.allocated[key] -= line["alloc"]
                line["alloc"] = 0
                line["status"] = "CANCELLED"
                continue
            if line["cancellation"] == "COMPANY" and day >= line["requested_ship_on"]:
                self.allocated[key] -= line["alloc"]
                line["alloc"] = 0
                line["status"] = "CANCELLED"
                line["company_cancel_on"] = day
                continue
            if line["hold"] and line["hold"]["start"] <= day <= line["hold"]["end"]:
                continue
            remaining = line["required_qty"] - line["shipped"]
            if day >= line["requested_ship_on"] - timedelta(days=2) and line["alloc"] < remaining:
                take = min(remaining - line["alloc"], max(0, self.free(key)))
                if take > 0:
                    line["alloc"] += take
                    self.allocated[key] += take
            if day >= line["requested_ship_on"] and line["alloc"] > 0 and is_business(day, line["facility_id"]):
                full = line["alloc"] >= remaining
                late = (day - line["requested_ship_on"]).days >= 3
                if full or late:
                    self.dispatch(day, line, line["alloc"])

    def dispatch(self, day: date, line: dict, qty: int, *, plan: dict | None = None) -> None:
        key = (line["item_id"], line["facility_id"])
        self.on_hand[key] -= qty
        self.allocated[key] -= qty
        if not line.get("scripted"):
            line["alloc"] -= qty
        line["shipped"] += qty
        if line["shipped"] >= line["required_qty"]:
            line["status"] = "SHIPPED"
        rng = self.rng["transit"]
        origin_tz = facility(line["facility_id"])["timezone"]
        ship_to = next(st for st in self.customers[line["customer_id"]]["ship_tos"] if st["ship_to_id"] == line["ship_to_id"])
        dest_tz = ship_to["timezone"]
        shipment_id = plan["shipment_id"] if plan else self.next_id("SH")
        confirm_visible = plan["confirm_visible"] if plan else utc_at(day, 18, origin_tz) + timedelta(hours=float(rng.uniform(1, 20)))
        shipment = {"shipment_id": shipment_id, "line_id": line["line_id"], "item_id": line["item_id"], "facility_id": line["facility_id"],
                    "qty": qty, "ship_on": day, "visible_at": confirm_visible}
        if line.get("silent_substitute"):
            shipment["shipped_item_id"] = self._substitute_for(line["item_id"])
        self.shipments.append(shipment)
        if plan:
            for event in plan["events"]:
                self.deliveries.append({"event_id": event["event_id"], "shipment_id": shipment_id, "line_id": line["line_id"], **event})
            return
        if line["incoterm"] in ("EXW", "FCA"):
            ready_at = utc_at(day, 8 + float(rng.uniform(0, 3)), origin_tz)
            self.deliveries.append({"event_id": self.next_id("EV"), "shipment_id": shipment_id, "line_id": line["line_id"], "kind": "READY",
                                    "on": day, "qty": qty, "local_hour": 8.5, "tz": origin_tz, "visible_at": ready_at + timedelta(hours=float(rng.uniform(1, 12))),
                                    "location_id": line["facility_id"]})
            return
        geo = line["geography_id"]
        mu = self.transit_estimate(line["facility_id"], geo)
        transit = max(1, int(round(float(rng.lognormal(mean=0, sigma=0.35)) * mu)))
        if geo == "GEO-MIDWEST" and date(2026, 1, 12) <= day <= date(2026, 2, 6):
            transit += int(rng.integers(2, 5))
        if geo == "GEO-NORTHEAST" and date(2025, 12, 15) <= day <= date(2026, 1, 9):
            transit += int(rng.integers(1, 3))
        arrive = next_business(day + timedelta(days=transit))
        roll = float(rng.random())
        if roll < 0.03:
            self._delivery(line, shipment_id, "ATTEMPT", arrive, qty, dest_tz, rng)
            arrive = add_business(arrive, 1)
        elif roll < 0.04:
            self._delivery(line, shipment_id, "MISDELIVERY", arrive, qty, dest_tz, rng)
            arrive = add_business(arrive, int(rng.integers(2, 4)))
        self._delivery(line, shipment_id, "POD", arrive, qty, dest_tz, rng)

    def _delivery(self, line, shipment_id, kind, day, qty, tz, rng) -> None:
        hour = 9 + float(rng.uniform(0, 8))
        moment = utc_at(day, hour, tz)
        lag = timedelta(hours=float(rng.uniform(1, 30)))
        if kind == "POD" and float(rng.random()) < 0.05:
            lag += timedelta(days=float(rng.uniform(5, 12)))
        self.deliveries.append({"event_id": self.next_id("EV"), "shipment_id": shipment_id, "line_id": line["line_id"], "kind": kind,
                                "on": day, "qty": qty, "local_hour": hour, "tz": tz, "visible_at": moment + lag, "location_id": line["ship_to_id"]})

    def _substitute_for(self, item_id: str) -> str:
        number = int(item_id.split("-")[1])
        return f"MM-{401 + (number - 400) % 40}"

    # ----- snapshots and feedback ----------------------------------------------------------
    def snapshot(self, day: date) -> None:
        rng = self.rng["production"]
        keys = sorted(set(self.on_hand) | set(self.in_transit))
        for item_id, facility_id in keys:
            key = (item_id, facility_id)
            if self.on_hand[key] == 0 and self.in_transit[key] == 0 and self.allocated[key] == 0:
                continue
            tz = facility(facility_id)["timezone"]
            taken = utc_at(day, 22, tz)
            on_hand = self.on_hand[key]
            book = on_hand + int(rng.integers(-3, 4)) if float(rng.random()) < 0.25 else on_hand
            self.snapshots.append({"snapshot_id": self.next_id("SNAP"), "item_id": item_id, "facility_id": facility_id,
                                   "on_hand": on_hand, "quality_hold": self.held(key), "allocated": self.allocated[key],
                                   "in_transit": self.in_transit[key], "erp_book": max(0, book), "taken_at": taken,
                                   "visible_at": taken + timedelta(hours=float(rng.uniform(4, 9))), "on": day})

    def feedback(self) -> None:
        rng = self.rng["feedback"]
        pods = defaultdict(list)
        for event in self.deliveries:
            if event["kind"] in ("POD", "READY"):
                pods[event["line_id"]].append(event)
        for line in self.so_lines:
            if line.get("scripted"):
                continue
            events = pods.get(line["line_id"])
            if not events:
                continue
            last = max(event["on"] for event in events)
            late = max(0, (last - line["original_promise_on"]).days)
            if float(rng.random()) < 0.7:
                score = 4.4 - 0.45 * min(late, 6) + float(rng.normal(0, 0.9))
                rating = int(min(5, max(1, round(score))))
                self.ratings.append({"line_id": line["line_id"], "rating": rating, "on": last + timedelta(days=int(rng.integers(1, 6))),
                                     "comment": None if rating >= 3 else "Delivery arrived later than promised." if late else "Packaging damaged on arrival."})
            if float(rng.random()) < 0.02:
                self.returns.append({"line_id": line["line_id"], "qty": max(1, line["shipped"] // 3), "on": last + timedelta(days=int(rng.integers(5, 20)))})

    # ----- the hero scenario --------------------------------------------------------------------
    def schedule_hero(self) -> None:
        """Hand-specified May 2026 records. Fixture: data/fixtures/hero_world_v1.json."""
        tz = "America/New_York"

        def at(text: str) -> datetime:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))

        hero_pos = [
            ("PO-2605-A1", 100, date(2026, 5, 1), date(2026, 5, 6),
             {"ack_on": date(2026, 5, 5), "promise_on": date(2026, 5, 6), "visible_at": at("2026-05-05T16:00:00Z")},
             [(date(2026, 5, 6), 100, "GR-2605-A1", [("ACCEPT", 100, date(2026, 5, 6))], None, at("2026-05-06T18:00:00Z"))]),
            ("PO-2605-B1", 100, date(2026, 5, 4), date(2026, 5, 11), None,
             [(date(2026, 5, 12), 60, "GR-2605-B1", [("ACCEPT", 40, date(2026, 5, 12)), ("SUPPLIER_REJECT", 20, date(2026, 5, 12))], None, at("2026-05-12T18:00:00Z"))]),
            ("PO-2605-C1", 50, date(2026, 5, 4), date(2026, 5, 8), None,
             [(date(2026, 5, 8), 50, "GR-2605-C1", [("ACCEPT", 50, date(2026, 5, 8))], (50, date(2026, 5, 9), date(2026, 6, 12)), at("2026-05-08T18:00:00Z"))]),
        ]
        self.hero_receipts = []
        self.hero_on_order = {}
        for line_id, qty, issued, requested, ack, receipts in hero_pos:
            line = self.issue_po(issued, "MM-440", "FAC-DAYTON", qty, hero={"line_id": line_id, "fields": {"buyer_requested_on": requested, "ack": ack}})
            for when, amount, receipt_id, dispositions, plant_hold, visible in receipts:
                # Counted as on order from the issue date, not from the start of the world, or MM-440 never reorders.
                self.hero_on_order[issued] = self.hero_on_order.get(issued, 0) + amount
                self.arrivals[when].append({"line": line, "qty": amount, "receipt_id": receipt_id, "disposition": dispositions,
                                            "plant_hold": plant_hold, "skip_costs": True, "visible": visible})
                self.hero_receipts.append(receipt_id)

        customers = {"CUS-001": self.customers["CUS-001"], "CUS-002": self.customers["CUS-002"]}
        lines = [
            ("SO-2605-N1-10", "CUS-001", date(2026, 4, 27), date(2026, 5, 6), date(2026, 5, 8), None,
             [(date(2026, 5, 6), 10, "2026-05-07T20:00:00Z", [("POD", "2026-05-07", 10, "2026-05-07T20:00:00Z")])]),
            ("SO-2605-N2-10", "CUS-002", date(2026, 4, 28), date(2026, 5, 8), date(2026, 5, 12), None,
             [(date(2026, 5, 8), 6, "2026-05-09T20:00:00Z", [("POD", "2026-05-12", 6, "2026-05-12T20:00:00Z")]),
              (date(2026, 5, 19), 4, "2026-05-20T20:00:00Z", [("POD", "2026-05-20", 4, "2026-05-20T20:00:00Z")])]),
            ("SO-2605-N3-10", "CUS-001", date(2026, 4, 30), date(2026, 5, 11), date(2026, 5, 15), None,
             [(date(2026, 5, 11), 10, "2026-05-11T22:00:00Z", [("ATTEMPT", "2026-05-14", 10, "2026-05-14T20:00:00Z"),
                                                                ("MISDELIVERY", "2026-05-16", 10, "2026-05-16T20:00:00Z"),
                                                                ("POD", "2026-05-18", 10, "2026-05-18T20:00:00Z")])]),
            ("SO-2605-N4-10", "CUS-002", date(2026, 5, 1), date(2026, 5, 13), date(2026, 5, 18),
             {"promise_on": date(2026, 5, 28), "recorded_on": date(2026, 5, 14)},
             [(date(2026, 5, 20), 10, "2026-05-20T20:00:00Z", [("POD", "2026-05-22", 10, "2026-05-22T20:00:00Z")])]),
        ]
        self.hero_ship_plans = defaultdict(list)
        for line_id, customer_id, ordered_on, requested, promise, revision, ships in lines:
            customer = customers[customer_id]
            ship_to = customer["ship_tos"][0]
            assert ship_to["geography_id"] == "GEO-NORTHEAST"
            line = self.add_so_line(ordered_on, line_id.rsplit("-", 1)[0], 0, customer, ship_to, "MM-440", 10, "FAC-DAYTON", requested, promise, "DAP",
                                    hero={"line_id": line_id, "fields": {"scripted": True, "revisions": [revision] if revision else []}})
            for index, (ship_on, qty, confirm_visible, events) in enumerate(ships):
                plan = {"shipment_id": f"SH-{line_id[3:]}-{index + 1}", "confirm_visible": at(confirm_visible),
                        "events": [{"event_id": f"EV-{line_id[3:]}-{index + 1}{position}", "kind": kind, "on": date.fromisoformat(on), "qty": amount,
                                    "local_hour": 15.0, "tz": tz, "visible_at": at(visible), "location_id": ship_to["ship_to_id"]}
                                   for position, (kind, on, amount, visible) in enumerate(events)]}
                self.hero_ship_plans[ship_on].append((line, qty, plan))
        self.hero_feedback = [
            {"line_id": "SO-2605-N1-10", "rating": 1, "on": date(2026, 5, 9), "comment": "Two units arrived with damaged terminal boxes."},
            {"line_id": "SO-2605-N4-10", "rating": 5, "on": date(2026, 5, 24), "comment": None},
        ]
        self.hero_returns = [{"line_id": "SO-2605-N1-10", "qty": 2, "on": date(2026, 5, 20)}]

    def hero_costs(self) -> None:
        """Landed-cost documents for the three hero receipts (one shared freight invoice)."""
        weights = {"GR-2605-A1": 10, "GR-2605-B1": 4, "GR-2605-C1": 5}
        brokerage = {"GR-2605-A1": 5000, "GR-2605-B1": 2000, "GR-2605-C1": 2500}
        obligation = datetime(2026, 5, 20, tzinfo=UTC)
        amounts_visible = datetime(2026, 6, 20, tzinfo=UTC)
        for receipt in self.receipts:
            if receipt["receipt_id"] not in weights:
                continue
            accepted = receipt["accepted_qty"]
            visible = datetime.combine(receipt["accepted_on"], datetime.min.time(), UTC) + timedelta(days=1, hours=12)
            self.costs.append({"receipt_id": receipt["receipt_id"], "kind": "MERCHANDISE", "document_id": f"INV-{receipt['receipt_id'][3:]}",
                               "obligation_visible_at": visible, "amount_minor": 1000 * accepted, "amount_visible_at": visible,
                               "currency": "USD", "invoice_date": receipt["accepted_on"], "economic_date": receipt["accepted_on"]})
            self.costs.append({"receipt_id": receipt["receipt_id"], "kind": "BROKERAGE", "document_id": f"BRK-{receipt['receipt_id'][3:]}",
                               "obligation_visible_at": obligation, "amount_minor": brokerage[receipt["receipt_id"]], "amount_visible_at": amounts_visible,
                               "currency": "USD", "economic_date": date(2026, 6, 18), "customs_value_minor": 1000 * accepted})
        self.freight_pools["FRT-HERO-2605"] = {
            "pool_id": "FRT-HERO-2605", "lane": "LN-US-FAC-DAYTON", "currency": "USD", "week": date(2026, 5, 4), "hero": True,
            "members": [{"receipt_id": key, "chargeable_weight": value, "volume": None} for key, value in weights.items()],
            "amount_minor": 38000, "invoice_date": date(2026, 6, 18), "obligation_visible_at": obligation, "amount_visible_at": amounts_visible,
        }

    # ----- main loop -------------------------------------------------------------------------------
    def run(self) -> "World":
        self.build_fx()
        self.schedule_hero()
        self.opening_stock()
        day = START
        while day <= END:
            self.on_order[("MM-440", "FAC-DAYTON")] += self.hero_on_order.pop(day, 0)
            for key, holds in list(self.holds.items()):
                self.holds[key] = [hold for hold in holds if hold["release"] > day]
            for arrival in self.arrivals.pop(day, []):
                self.receive(day, arrival)
            for order in self.completions.pop(day, []):
                self.complete(day, order)
            for transfer in self.transfer_arrivals.pop(day, []):
                key = (transfer["item_id"], transfer["to_id"])
                self.in_transit[key] -= transfer["qty"]
                self.on_hand[key] += transfer["qty"]
            if day.weekday() == 0 and day <= ORDER_END:
                self.plan_purchasing(day)
                self.plan_production(day)
            if day.weekday() == 2:
                self.replenish(day)
            self.create_orders(day)
            if day == HERO_RESERVE_ON:
                for plans in self.hero_ship_plans.values():
                    for line, qty, _ in plans:
                        self.allocated[(line["item_id"], line["facility_id"])] += qty
            for line, qty, plan in self.hero_ship_plans.pop(day, []):
                self.dispatch(day, line, qty, plan=plan)
            self.ship(day)
            if day.weekday() == 4:
                self.snapshot(day)
            day += timedelta(days=1)
        self.hero_costs()
        self.close_freight_pools()
        self.feedback()
        self.ratings.extend(self.hero_feedback)
        self.returns.extend(self.hero_returns)
        return self

    def opening_stock(self) -> None:
        for (item_id, serving), weekly in self.fg_weekly.items():
            self.on_hand[(item_id, serving)] += int(2 * weekly) + 6
        for (item_id, plant), weekly in self.plant_weekly.items():
            self.on_hand[(item_id, plant)] += int(2 * weekly) + 10
        for (item_id, plant), weekly in self.component_weekly.items():
            self.on_hand[(item_id, plant)] += int(4 * weekly) + 20


def build_world() -> World:
    return World().run()


def facilities() -> tuple:
    return FACILITIES
