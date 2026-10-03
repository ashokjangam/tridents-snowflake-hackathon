"""Project simulator truth into six synthetic source systems.

Each source sees only its own slice, with its own identifiers, units, clocks,
and extraction delays. Defects are injected from the `defects` stream and
catalogued in hidden truth. Output files are what Snowflake ingests.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from concordia.hashing import canonical_json, sha256_canonical
from sim.engine import END, UTC, World, iso
from sim.master import CALENDARS, FACILITY_CALENDAR, GEOGRAPHIES, facility
from sim.world import FACILITIES

GENERATOR_VERSION = "concordia-sim-1.0.0"
CONTRACT = "CONCORDIA_SIM_V1"
BATCH_CUTOFF = datetime(2026, 6, 5, 23, 59, 59, tzinfo=UTC)

PLANT_CODE = {"FAC-DAYTON": "US10", "FAC-RENO": "US20", "FAC-STUTTGART": "DE10",
              "DC-NEWARK": "US30", "DC-OAKLAND": "US40", "DC-HAMBURG": "DE20"}
MES_PLANT = {"FAC-DAYTON": "DAY", "FAC-RENO": "REN", "FAC-STUTTGART": "STU"}
SITE_GLN = {fid: f"GLN-0861234-{index + 1:04d}" for index, fid in enumerate(PLANT_CODE)}
REGION_NAME = {row["geography_id"]: row["name"] for row in GEOGRAPHIES}


def gtin(item_id: str) -> str:
    prefix, number = item_id.split("-")
    family = {"MM": "1", "SA": "2", "CP": "3"}[prefix]
    return f"08612345{family}{int(number):04d}"


def mes_code(item_id: str) -> str:
    return item_id.replace("-", "")


def vendor_no(supplier_id: str) -> str:
    return f"V-{10000 + int(supplier_id[-3:])}"


def customer_no(customer_id: str) -> str:
    return f"C-{20000 + int(customer_id[-3:])}"


def erp_ship_to(ship_to_id: str) -> str:
    customer, site = ship_to_id.rsplit("-ST", 1)
    return f"{customer_no(customer)}-{int(site):02d}"


def crm_account(customer_id: str) -> str:
    return f"ACC-{7000 + int(customer_id[-3:])}"


def crm_site(ship_to_id: str) -> str:
    customer, site = ship_to_id.rsplit("-ST", 1)
    return f"SITE-{int(customer[-3:]):03d}{site}"


def ship_to_gln(ship_to_id: str) -> str:
    customer, site = ship_to_id.rsplit("-ST", 1)
    return f"GLN-4400{int(customer[-3:]):03d}-{int(site):02d}"


def d(value: date | None) -> str | None:
    return value.isoformat() if value else None


def local_naive(moment: datetime, zone: str) -> str:
    return moment.astimezone(ZoneInfo(zone)).strftime("%Y-%m-%dT%H:%M:%S")


class Projector:
    def __init__(self, world: World) -> None:
        self.world = world
        self.rng = world.rng["defects"]
        self.records: dict[str, list[dict]] = defaultdict(list)
        self.defects: list[dict] = []
        self.revision_of: dict[tuple, int] = defaultdict(int)

    # ----- envelope ---------------------------------------------------------------------------------
    def emit(self, system: str, obj: str, record_id: str, payload: dict, visible: datetime, *,
             stream: str, recorded: datetime | None = None, revision: int | None = None) -> dict:
        if revision is None:
            self.revision_of[(system, obj, record_id)] += 1
            revision = self.revision_of[(system, obj, record_id)]
        recorded = recorded or (visible - timedelta(minutes=30))
        row = {
            "source_system": system,
            "source_object": obj,
            "source_record_id": record_id,
            "source_revision": revision,
            "recorded_at": iso(recorded),
            "extracted_at": iso(visible),
            "visible_at": iso(visible),
            "origin": f"SYNTHETIC_{system}",
            "generator_version": GENERATOR_VERSION,
            "seed_stream": stream,
            "scenario_id": CONTRACT,
            "payload": payload,
        }
        row["payload_hash"] = sha256_canonical(payload)
        self.records[system].append(row)
        return row

    def defect(self, kind: str, system: str, record_id: str, detail: str) -> None:
        self.defects.append({"defect_id": f"DEF-{len(self.defects) + 1:05d}", "kind": kind, "source_system": system,
                             "source_record_id": record_id, "detail": detail})

    def roll(self) -> float:
        return float(self.rng.random())

    def date_text(self, value: date, plant: str) -> str:
        """ERP plant users key dates in local formats on ~8% of manual documents."""
        if self.roll() < 0.08:
            if facility(plant)["country"] == "DE":
                return value.strftime("%d.%m.%Y")
            return value.strftime("%m/%d/%Y")
        return value.isoformat()

    # ----- masters ------------------------------------------------------------------------------------
    def masters(self) -> None:
        w = self.world
        epoch = datetime(2024, 12, 20, 12, tzinfo=UTC)
        for supplier in w.master["suppliers"]:
            self.emit("ERP", "VENDOR", vendor_no(supplier["supplier_id"]),
                      {"vendor_no": vendor_no(supplier["supplier_id"]), "name": supplier["name"], "country": supplier["country"],
                       "currency": supplier["currency"]}, epoch, stream="supply")
        self.emit("ERP", "VENDOR", "V-10001-A", {"vendor_no": "V-10001-A", "name": "APEX BEARINGS INC (OLD)", "country": "US", "currency": "USD"},
                  epoch, stream="defects")
        self.defect("DUPLICATE_VENDOR", "ERP", "V-10001-A", "Legacy vendor record for Apex Bearings; administered alias maps it to SUP-001.")
        for item in w.master["items"]:
            kind = {"FINISHED": "FERT", "SUBASSEMBLY": "HALB", "COMPONENT": "ROH"}[item["item_type"]]
            self.emit("ERP", "MATERIAL", item["item_id"], {"material_no": item["item_id"], "description": item["name"], "material_type": kind,
                                                           "base_uom": "EA", "weight_kg": str(item["unit_weight_kg"])}, epoch, stream="supply")
        for customer in w.customers.values():
            self.emit("ERP", "CUSTOMER", customer_no(customer["customer_id"]),
                      {"customer_no": customer_no(customer["customer_id"]), "name": customer["name"].upper()}, epoch, stream="demand")
            parent = customer["parent_customer_id"]
            self.emit("CRM", "ACCOUNT", crm_account(customer["customer_id"]),
                      {"account_id": crm_account(customer["customer_id"]), "name": customer["name"],
                       "parent_account_id": crm_account(parent) if parent else None, "region": REGION_NAME[customer["geography_id"]]},
                      epoch, stream="demand")
            for site in customer["ship_tos"]:
                self.emit("CRM", "SHIP_TO", crm_site(site["ship_to_id"]),
                          {"ship_to_id": crm_site(site["ship_to_id"]), "account_id": crm_account(customer["customer_id"]),
                           "erp_ship_to": erp_ship_to(site["ship_to_id"]), "gln": ship_to_gln(site["ship_to_id"]),
                           "region": REGION_NAME[site["geography_id"]], "timezone": site["timezone"], "calendar": site["calendar_id"]},
                          epoch, stream="demand")
        for row in w.master["bom"]:
            record_id = f"{mes_code(row['parent_id'])}/{mes_code(row['component_id'])}/{row['revision']}"
            self.emit("MES", "BOM_LINE", record_id,
                      {"parent": mes_code(row["parent_id"]), "component": mes_code(row["component_id"]), "qty_per": str(row["qty_per"]),
                       "revision": row["revision"], "valid_from": row["effective_from"], "valid_to": row["effective_to"]}, epoch, stream="production")

    # ----- purchasing ---------------------------------------------------------------------------------
    def purchasing(self) -> None:
        w = self.world
        receipts_by_line = defaultdict(list)
        for receipt in w.receipts:
            receipts_by_line[receipt["line_id"]].append(receipt)
        for line in w.po_lines:
            plant = line["facility_id"]
            tz = facility(plant)["timezone"]
            issued_visible = datetime.combine(line["issued_on"], datetime.min.time(), ZoneInfo(tz)).astimezone(UTC) + timedelta(hours=18)
            vendor = vendor_no(line["supplier_id"])
            if line["supplier_id"] == "SUP-001" and not line["hero"] and self.roll() < 0.15:
                vendor = "V-10001-A"
            uom, qty = "EA", line["ordered_qty"]
            if not line["hero"] and line["item_id"].startswith("CP-") and qty % 12 == 0 and self.roll() < 0.25:
                uom, qty = "CASE", qty // 12
            payload = {"po_line_no": line["line_id"], "vendor_no": vendor, "material_no": line["item_id"], "plant_code": PLANT_CODE[plant],
                       "qty": str(qty), "uom": uom, "issued": self.date_text(line["issued_on"], plant) if not line["hero"] else d(line["issued_on"]),
                       "requested": d(line["buyer_requested_on"]), "incoterm": line["incoterm"]}
            if not line["hero"]:
                roll = self.roll()
                if roll < 0.004:
                    payload["vendor_no"] = f"V-{10000 + int(line['supplier_id'][-3:])}-X"
                    self.defect("UNMAPPED_VENDOR", "ERP", line["line_id"], "Vendor number keyed with a suffix that has no administered alias.")
                elif roll < 0.007:
                    payload["uom"] = "PALLET"
                    self.defect("UNRESOLVED_UOM", "ERP", line["line_id"], "PALLET has no governed conversion for this item.")
            self.emit("ERP", "PO_LINE", line["line_id"], payload, issued_visible, stream="supply")
            if line["ack"]:
                ack = line["ack"]
                self.emit("ERP", "PO_ACK", line["line_id"], {"po_line_no": line["line_id"], "ack_date": d(ack["ack_on"]),
                                                             "promised_date": d(ack["promise_on"])}, ack["visible_at"], stream="supply")
            if line["cancellation"]:
                when = line["issued_on"] + timedelta(days=1 if line["cancellation"] == "BUYER_BEFORE_COMMITMENT" else 20)
                self.emit("ERP", "PO_CANCEL", line["line_id"], {"po_line_no": line["line_id"], "reason": line["cancellation"], "date": d(when)},
                          datetime.combine(when, datetime.min.time(), UTC) + timedelta(hours=20), stream="supply")
        missing_disposition = set()
        for receipt in w.receipts:
            plant = receipt["facility_id"]
            uom, qty = "EA", receipt["qty"]
            if receipt["item_id"].startswith("CP-") and qty % 12 == 0 and self.roll() < 0.3:
                uom, qty = "CASE", qty // 12
            self.emit("WMS", "RECEIPT", receipt["receipt_id"],
                      {"receipt_no": receipt["receipt_id"], "po_ref": receipt["line_id"], "gtin": gtin(receipt["item_id"]), "site": SITE_GLN[plant],
                       "qty": str(qty), "uom": uom, "received_date": d(receipt["received_on"]),
                       "lot_id": f"LOT-R-{receipt['receipt_id']}"}, receipt["visible_at"], stream="quality")
            if receipt["receipt_id"] not in w.hero_receipts and self.roll() < 0.006:
                missing_disposition.add(receipt["receipt_id"])
                self.defect("DISPOSITION_MISSING", "MES", receipt["receipt_id"], "Receipt has no quality disposition in MES.")
        for index, event in enumerate(w.dispositions):
            if event["receipt_id"] in missing_disposition:
                continue
            tz = facility(event["facility_id"])["timezone"]
            record_id = f"QD-{event['receipt_id']}-{event['kind']}"
            self.emit("MES", "DISPOSITION", record_id,
                      {"disp_no": record_id, "receipt_ref": event["receipt_id"], "item": mes_code(event["item_id"]), "plant": MES_PLANT[event["facility_id"]],
                       "kind": event["kind"], "qty": str(event["qty"]), "local_ts": local_naive(event["visible_at"] - timedelta(minutes=45), tz),
                       "release_on": d(event.get("release_on"))}, event["visible_at"], stream="quality")

    # ----- production ---------------------------------------------------------------------------------
    def production(self) -> None:
        w = self.world
        for order in w.production:
            tz = facility(order["facility_id"])["timezone"]
            visible = datetime.combine(order["complete_on"], datetime.min.time(), ZoneInfo(tz)).astimezone(UTC) + timedelta(hours=20)
            self.emit("MES", "WORK_ORDER", order["order_id"],
                      {"wo_no": order["order_id"], "item": mes_code(order["item_id"]), "plant": MES_PLANT[order["facility_id"]], "qty": str(order["qty"]),
                       "start": d(order["start_on"]), "complete": d(order["complete_on"])}, visible, stream="production")
            if order.get("plant_hold"):
                hold = order["plant_hold"]
                self.emit("MES", "PRODUCTION_HOLD", order["order_id"],
                          {"wo_no": order["order_id"], "item": mes_code(order["item_id"]), "plant": MES_PLANT[order["facility_id"]],
                           "qty": str(hold["qty"]), "start": d(hold["start_on"]), "release": d(hold["release_on"])}, visible, stream="quality")
        for issue in w.issues:
            tz = facility(issue["facility_id"])["timezone"]
            self.emit("MES", "MATERIAL_ISSUE", issue["issue_id"],
                      {"issue_no": issue["issue_id"], "wo_no": issue["order_id"], "component": mes_code(issue["component_id"]),
                       "plant": MES_PLANT[issue["facility_id"]], "qty": str(issue["qty"]),
                       "issued_local": f"{d(issue['on'])}T07:30:00", "bom_revision": issue["revision"]}, issue["visible_at"], stream="production")

    # ----- sales, shipping, delivery ---------------------------------------------------------------------
    def sales(self) -> None:
        w = self.world
        for line in w.so_lines:
            serving = line["facility_id"]
            tz = facility(serving)["timezone"]
            visible = datetime.combine(line["order_on"], datetime.min.time(), ZoneInfo(tz)).astimezone(UTC) + timedelta(hours=19)
            incoterm = line["incoterm"]
            payload = {"so_line_no": line["line_id"], "customer_no": customer_no(line["customer_id"]), "ship_to_no": erp_ship_to(line["ship_to_id"]),
                       "material_no": line["item_id"], "ship_from": PLANT_CODE[serving], "qty": str(line["ordered_qty"]), "uom": "EA",
                       "incoterm": incoterm, "order_date": d(line["order_on"]), "requested_ship": d(line["requested_ship_on"])}
            if not line["hero"]:
                roll = self.roll()
                if roll < 0.004:
                    payload["incoterm"] = None
                    self.defect("INCOTERM_MISSING", "ERP", line["line_id"], "Sales line saved without an Incoterm.")
                elif roll < 0.007:
                    payload["incoterm"] = "CIF"
                    self.defect("INCOTERM_UNSUPPORTED", "ERP", line["line_id"], "CIF is outside the v1 supported Incoterm set.")
                elif roll < 0.010:
                    payload["ship_to_no"] = payload["ship_to_no"] + "X"
                    self.defect("UNMAPPED_SHIP_TO", "ERP", line["line_id"], "Ship-to keyed with a trailing character; no administered alias.")
                elif roll < 0.012:
                    payload["uom"] = "PALLET"
                    self.defect("UNRESOLVED_UOM", "ERP", line["line_id"], "PALLET has no governed conversion for this item.")
            self.emit("ERP", "SO_LINE", line["line_id"], payload, visible, stream="demand")
            self.emit("ERP", "SO_PROMISE", line["line_id"], {"so_line_no": line["line_id"], "promise_date": d(line["original_promise_on"]),
                                                             "kind": "ORIGINAL", "recorded_on": d(line["order_on"])}, visible + timedelta(minutes=5), stream="commercial")
            current = line["original_promise_on"]
            for revision in line["revisions"]:
                rec_visible = datetime.combine(revision["recorded_on"], datetime.min.time(), UTC) + timedelta(hours=16)
                self.emit("ERP", "SO_PROMISE", line["line_id"], {"so_line_no": line["line_id"], "promise_date": d(revision["promise_on"]),
                                                                 "kind": "REVISED", "recorded_on": d(revision["recorded_on"])}, rec_visible, stream="commercial")
                current = revision["promise_on"]
            if line["revisions"]:
                self.emit("CRM", "PROMISE_CURRENT", line["line_id"], {"so_ref": line["line_id"], "promise_date": d(current)},
                          datetime.combine(line["revisions"][-1]["recorded_on"], datetime.min.time(), UTC) + timedelta(hours=17), stream="commercial")
                self.defect("PROMISE_OVERWRITE", "CRM", line["line_id"], "CRM keeps only the latest promise; ERP keeps the original.")
            if line["cancellation"] == "CUSTOMER_BEFORE_PICK":
                self.emit("ERP", "SO_CHANGE", line["line_id"], {"so_line_no": line["line_id"], "change_type": "CUSTOMER_CANCEL", "qty": None,
                                                                "approved_on": d(line["cancel_on"])},
                          datetime.combine(line["cancel_on"], datetime.min.time(), UTC) + timedelta(hours=15), stream="commercial")
            if line["cancellation"] == "COMPANY" and line.get("company_cancel_on"):
                self.emit("ERP", "SO_CHANGE", line["line_id"], {"so_line_no": line["line_id"], "change_type": "COMPANY_CANCEL", "qty": None,
                                                                "approved_on": d(line["company_cancel_on"])},
                          datetime.combine(line["company_cancel_on"], datetime.min.time(), UTC) + timedelta(hours=15), stream="commercial")
            if line["short_close"]:
                approved = line["short_close"]["approved_on"]
                self.emit("ERP", "SO_CHANGE", line["line_id"], {"so_line_no": line["line_id"], "change_type": "SHORT_CLOSE",
                                                                "qty": str(line["short_close"]["qty"]), "approved_on": d(approved)},
                          datetime.combine(approved, datetime.min.time(), UTC) + timedelta(hours=15), stream="commercial")
            if line["hold"]:
                hold = line["hold"]
                self.emit("CRM", "CUSTOMER_HOLD", line["line_id"], {"so_ref": line["line_id"], "start": d(hold["start"]), "end": d(hold["end"]),
                                                                    "recorded": d(hold["recorded_on"])},
                          datetime.combine(hold["recorded_on"], datetime.min.time(), UTC) + timedelta(hours=14), stream="commercial")
        lines = {line["line_id"]: line for line in w.so_lines}
        for shipment in w.shipments:
            line = lines[shipment["line_id"]]
            shipped_item = shipment.get("shipped_item_id", shipment["item_id"])
            if shipped_item != shipment["item_id"]:
                self.defect("SILENT_SUBSTITUTE", "WMS", shipment["shipment_id"], f"Shipped {shipped_item} against a line for {shipment['item_id']} with no approved substitution.")
            self.emit("WMS", "SHIP_CONFIRM", shipment["shipment_id"],
                      {"ship_no": shipment["shipment_id"], "so_ref": shipment["line_id"], "gtin": gtin(shipped_item), "site": SITE_GLN[line["facility_id"]],
                       "qty": str(shipment["qty"]), "uom": "EA", "ship_date": d(shipment["ship_on"]),
                       "lot_id": f"LOT-S-{shipment['shipment_id']}"}, shipment["visible_at"], stream="transit")
        for event in w.deliveries:
            line = lines[event["line_id"]]
            moment = datetime.combine(event["on"], datetime.min.time(), ZoneInfo(event["tz"])) + timedelta(hours=event["local_hour"])
            tz_value = event["tz"]
            if not line["hero"] and self.roll() < 0.012:
                tz_value = None
                self.defect("TIMEZONE_MISSING", "TMS", event["event_id"], "Carrier event arrived without a timezone or offset.")
            location = SITE_GLN[line["facility_id"]] if event["kind"] == "READY" else ship_to_gln(line["ship_to_id"])
            self.emit("TMS", "DELIVERY_EVENT", event["event_id"],
                      {"event_no": event["event_id"], "shipment_ref": event["shipment_id"], "so_ref": event["line_id"], "event_type": event["kind"],
                       "qty": str(event["qty"]), "local_ts": moment.strftime("%Y-%m-%dT%H:%M:%S"), "tz": tz_value, "location": location},
                      event["visible_at"], stream="transit")
        for rating in w.ratings:
            visible = datetime.combine(rating["on"], datetime.min.time(), UTC) + timedelta(hours=15)
            self.emit("CRM", "RATING", rating["line_id"], {"so_ref": rating["line_id"], "rating": rating["rating"], "comment": rating["comment"],
                                                           "rated_on": d(rating["on"])}, visible, stream="feedback")
            if rating["rating"] <= 2:
                self.emit("CRM", "COMPLAINT", f"CASE-{rating['line_id']}", {"case_no": f"CASE-{rating['line_id']}", "so_ref": rating["line_id"],
                                                                         "text": rating["comment"] or "Customer reported a service problem.", "opened_on": d(rating["on"])},
                          visible + timedelta(hours=1), stream="feedback")
        for item in w.returns:
            visible = datetime.combine(item["on"], datetime.min.time(), UTC) + timedelta(hours=15)
            self.emit("CRM", "RETURN", item["line_id"], {"so_ref": item["line_id"], "qty": str(item["qty"]), "returned_on": d(item["on"])}, visible, stream="feedback")

    # ----- inventory ------------------------------------------------------------------------------------
    def inventory(self) -> None:
        w = self.world
        for snap in w.snapshots:
            tz = facility(snap["facility_id"])["timezone"]
            self.emit("WMS", "SNAPSHOT", snap["snapshot_id"],
                      {"snap_no": snap["snapshot_id"], "gtin": gtin(snap["item_id"]), "site": SITE_GLN[snap["facility_id"]], "on_hand": str(snap["on_hand"]),
                       "hold": str(snap["quality_hold"]), "allocated": str(snap["allocated"]), "in_transit": str(snap["in_transit"]), "uom": "EA",
                       "taken_local": local_naive(snap["taken_at"], tz)}, snap["visible_at"], stream="production")
            if snap["erp_book"] != snap["on_hand"]:
                self.emit("ERP", "BOOK_STOCK", snap["snapshot_id"], {"material_no": snap["item_id"], "plant_code": PLANT_CODE[snap["facility_id"]],
                                                                    "book_qty": str(snap["erp_book"]), "as_of": d(snap["on"])},
                          snap["visible_at"] + timedelta(hours=2), stream="production")
        for transfer in w.transfers:
            self.emit("WMS", "TRANSFER", transfer["transfer_id"],
                      {"transfer_no": transfer["transfer_id"], "gtin": gtin(transfer["item_id"]), "from_site": SITE_GLN[transfer["from_id"]],
                       "to_site": SITE_GLN[transfer["to_id"]], "qty": str(transfer["qty"]), "ship_date": d(transfer["ship_on"]),
                       "arrive_date": d(transfer["arrive_on"])}, transfer["visible_at"], stream="transit")

    # ----- IoT dock telemetry -----------------------------------------------------------------------
    def iot(self) -> None:
        """Synthetic gate and temperature readings tied to canonical receipt/shipment lots."""
        for index, receipt in enumerate(self.world.receipts):
            event_time = receipt["visible_at"] - timedelta(minutes=20)
            self.emit(
                "IOT",
                "DOCK_SENSOR",
                f"IOT-R-{receipt['receipt_id']}",
                {
                    "sensor_id": f"DOCK-{receipt['facility_id']}-IN-{index % 4 + 1}",
                    "event_type": "TRUCK_ARRIVAL",
                    "event_ts": iso(event_time),
                    "truck_id": f"TRK-{index % 73 + 1:03d}",
                    "receipt_ref": receipt["receipt_id"],
                    "shipment_ref": None,
                    "lot_id": f"LOT-R-{receipt['receipt_id']}",
                    "gtin": gtin(receipt["item_id"]),
                    "site": SITE_GLN[receipt["facility_id"]],
                    "temperature_c": f"{18.0 + (index % 17) / 10:.1f}",
                },
                receipt["visible_at"],
                stream="transit",
                recorded=event_time,
            )
        lines = {line["line_id"]: line for line in self.world.so_lines}
        for index, shipment in enumerate(self.world.shipments):
            line = lines[shipment["line_id"]]
            event_time = shipment["visible_at"] - timedelta(minutes=10)
            self.emit(
                "IOT",
                "DOCK_SENSOR",
                f"IOT-S-{shipment['shipment_id']}",
                {
                    "sensor_id": f"DOCK-{line['facility_id']}-OUT-{index % 4 + 1}",
                    "event_type": "TRUCK_DEPARTURE",
                    "event_ts": iso(event_time),
                    "truck_id": f"TRK-{index % 89 + 1:03d}",
                    "receipt_ref": None,
                    "shipment_ref": shipment["shipment_id"],
                    "lot_id": f"LOT-S-{shipment['shipment_id']}",
                    "gtin": gtin(shipment.get("shipped_item_id", shipment["item_id"])),
                    "site": SITE_GLN[line["facility_id"]],
                    "temperature_c": f"{18.5 + (index % 13) / 10:.1f}",
                },
                shipment["visible_at"],
                stream="transit",
                recorded=event_time,
            )

    # ----- landed cost documents --------------------------------------------------------------------------
    def costs(self) -> None:
        w = self.world
        receipts = {receipt["receipt_id"]: receipt for receipt in w.receipts}

        def money(minor: int | None, currency: str) -> str | None:
            if minor is None:
                return None
            return f"{minor / 100:.2f}"

        for cost in w.costs:
            receipt = receipts[cost["receipt_id"]]
            plant = receipt["facility_id"]
            base = {"doc_no": cost["document_id"], "doc_type": cost["kind"], "receipt_ref": cost["receipt_id"], "currency": cost["currency"],
                    "doc_date": d(cost.get("invoice_date")), "economic_date": d(cost.get("economic_date")),
                    "customs_value": money(cost.get("customs_value_minor"), "USD"), "merchandise_value": money(cost.get("merchandise_value_minor"), cost["currency"]),
                    "buyer_charged": bool(cost.get("buyer_charged", False))}
            if cost["kind"] == "MERCHANDISE":
                self.emit("ERP", "AP_DOC", cost["document_id"], {**base, "amount": money(cost["amount_minor"], cost["currency"])},
                          cost["amount_visible_at"], stream="commercial")
                continue
            self.emit("ERP", "AP_DOC", cost["document_id"], {**base, "amount": None}, cost["obligation_visible_at"], stream="commercial")
            if cost["amount_minor"] is not None:
                self.emit("ERP", "AP_DOC", cost["document_id"], {**base, "amount": money(cost["amount_minor"], cost["currency"])},
                          max(cost["amount_visible_at"], cost["obligation_visible_at"] + timedelta(minutes=1)), stream="commercial")
            elif cost["kind"] == "DUTY":
                self.defect("DUTY_NEVER_ARRIVED", "ERP", cost["document_id"], "Customs entry obligation recorded; assessed amount never posted.")
            del plant
        for pool in w.freight_pools.values():
            members = [{"receipt_ref": m["receipt_id"], "chargeable_weight_kg": None if m["chargeable_weight"] is None else str(m["chargeable_weight"]),
                        "volume_m3": None if m["volume"] is None else str(m["volume"])} for m in pool["members"]]
            if any(m["chargeable_weight"] is None for m in pool["members"]):
                self.defect("FREIGHT_WEIGHT_MISSING", "TMS", pool["pool_id"], "A pooled receipt lacks chargeable weight; allocation falls back to volume.")
            base = {"invoice_no": pool["pool_id"], "lane": pool["lane"], "currency": pool["currency"], "invoice_date": d(pool["invoice_date"]), "members": members}
            self.emit("TMS", "FREIGHT_INVOICE", pool["pool_id"], {**base, "amount": None}, pool["obligation_visible_at"], stream="commercial")
            self.emit("TMS", "FREIGHT_INVOICE", pool["pool_id"], {**base, "amount": f"{pool['amount_minor'] / 100:.2f}"},
                      max(pool["amount_visible_at"], pool["obligation_visible_at"] + timedelta(minutes=1)), stream="commercial")
        for row in w.fx:
            self.emit("ERP", "FX_RATE", f"{row['currency']}-{row['rate_date']}", {"currency": row["currency"], "rate_date": row["rate_date"],
                                                                                   "usd_per_unit": row["usd_per_unit"]},
                      datetime.fromisoformat(row["visible_at"].replace("Z", "+00:00")), stream="commercial")

    # ----- replays ------------------------------------------------------------------------------------
    def replays(self) -> None:
        for system, rows in self.records.items():
            extra = []
            for row in rows:
                if self.roll() < 0.01:
                    copy = dict(row)
                    copy["extracted_at"] = iso(datetime.fromisoformat(row["visible_at"].replace("Z", "+00:00")) + timedelta(days=2))
                    extra.append(copy)
            for row in extra:
                self.defect("DUPLICATE_DELIVERY", system, row["source_record_id"], "Identical record re-extracted; idempotent merge must ignore it.")
            rows.extend(extra)

    def run(self) -> "Projector":
        self.masters()
        self.purchasing()
        self.production()
        self.sales()
        self.inventory()
        self.iot()
        self.costs()
        self.replays()
        return self


def governance(world: World) -> dict:
    """Administered master data and aliases. This is the MDM contract, not hidden truth."""
    aliases = []

    def alias(system, entity, key, canonical, method="ADMINISTERED"):
        aliases.append({"source_system": system, "entity_type": entity, "source_key": key, "canonical_id": canonical, "method": method})

    for supplier in world.master["suppliers"]:
        alias("ERP", "SUPPLIER", vendor_no(supplier["supplier_id"]), supplier["supplier_id"])
    alias("ERP", "SUPPLIER", "V-10001-A", "SUP-001")
    for item in world.master["items"]:
        alias("ERP", "ITEM", item["item_id"], item["item_id"], "EXACT_KEY")
        alias("MES", "ITEM", mes_code(item["item_id"]), item["item_id"])
        alias("WMS", "ITEM", gtin(item["item_id"]), item["item_id"], "GTIN")
        alias("IOT", "ITEM", gtin(item["item_id"]), item["item_id"], "GTIN")
    for fid, code in PLANT_CODE.items():
        alias("ERP", "FACILITY", code, fid)
        alias("WMS", "FACILITY", SITE_GLN[fid], fid, "GLN")
        alias("IOT", "FACILITY", SITE_GLN[fid], fid, "GLN")
    for fid, code in MES_PLANT.items():
        alias("MES", "FACILITY", code, fid)
    for customer in world.customers.values():
        alias("ERP", "CUSTOMER", customer_no(customer["customer_id"]), customer["customer_id"])
        alias("CRM", "CUSTOMER", crm_account(customer["customer_id"]), customer["customer_id"])
        for site in customer["ship_tos"]:
            alias("ERP", "SHIP_TO", erp_ship_to(site["ship_to_id"]), site["ship_to_id"])
            alias("CRM", "SHIP_TO", crm_site(site["ship_to_id"]), site["ship_to_id"])
            alias("TMS", "SHIP_TO", ship_to_gln(site["ship_to_id"]), site["ship_to_id"], "GLN")
    items = [{"item_id": i["item_id"], "name": i["name"], "item_type": i["item_type"], "family": i["family"],
              "inventory_class": {"FINISHED": "FINISHED_GOODS", "SUBASSEMBLY": "WORK_IN_PROCESS", "COMPONENT": "RAW_MATERIAL"}[i["item_type"]],
              "home_facility_id": i["home_facility_id"], "unit_weight_kg": i["unit_weight_kg"]} for i in world.master["items"]]
    parties = [{"party_id": s["supplier_id"], "party_type": "SUPPLIER", "name": s["name"], "country": s["country"], "currency": s["currency"],
                "parent_party_id": s.get("parent_supplier_id"), "geography_id": None} for s in world.master["suppliers"]]
    parties += [{"party_id": c["customer_id"], "party_type": "CUSTOMER", "name": c["name"], "country": c["ship_tos"][0]["country"], "currency": None,
                 "parent_party_id": c["parent_customer_id"], "geography_id": c["geography_id"]} for c in world.customers.values()]
    ship_tos = [dict(site) for c in world.customers.values() for site in c["ship_tos"]]
    facilities = [{**row, "calendar_id": FACILITY_CALENDAR.get(row["facility_id"], "CAL-WEEKDAY")} for row in FACILITIES]
    supply = [dict(row) for row in world.master["supply"]]
    uom = [{"item_id": i["item_id"], "from_uom": "CASE", "to_uom": "EA", "factor": "12"} for i in world.master["items"] if i["item_type"] == "COMPONENT"]
    uom += [{"item_id": i["item_id"], "from_uom": "EA", "to_uom": "EA", "factor": "1"} for i in world.master["items"]]
    return {"aliases": aliases, "items": items, "parties": parties, "ship_tos": ship_tos, "facilities": facilities, "geographies": list(GEOGRAPHIES),
            "calendars": list(CALENDARS), "lanes": world.master["lanes"], "supply": supply,
            "substitutions": world.master["substitutions"], "uom": uom}


def truth(world: World) -> dict:
    """Hidden test-only truth. Product roles never read this."""
    def line_truth(line):
        return {"line_id": line["line_id"], "item_id": line["item_id"], "facility_id": line["facility_id"], "customer_id": line["customer_id"],
                "geography_id": line["geography_id"], "ordered_qty": line["ordered_qty"], "required_qty": line["required_qty"], "shipped": line["shipped"],
                "status": line["status"], "requested_ship_on": d(line["requested_ship_on"]), "original_promise_on": d(line["original_promise_on"]),
                "incoterm": line["incoterm"], "cancellation": line["cancellation"], "hero": line["hero"]}
    return {
        "so_lines": [line_truth(line) for line in world.so_lines],
        "po_lines": [{"line_id": l["line_id"], "supplier_id": l["supplier_id"], "item_id": l["item_id"], "facility_id": l["facility_id"],
                      "ordered_qty": l["ordered_qty"], "issued_on": d(l["issued_on"]), "buyer_requested_on": d(l["buyer_requested_on"]),
                      "accepted_qty": sum(r.get("accepted_qty", 0) for r in l["receipts"]), "cancellation": l["cancellation"], "hero": l["hero"]}
                     for l in world.po_lines],
        "hero_receipts": world.hero_receipts,
    }


def write(out: Path, world: World | None = None) -> dict:
    from sim.engine import build_world

    world = world or build_world()
    projector = Projector(world).run()
    out.mkdir(parents=True, exist_ok=True)
    (out / "sources").mkdir(exist_ok=True)
    files = {}
    for system, rows in sorted(projector.records.items()):
        for batch, keep in (("b1", lambda r: r["extracted_at"] <= iso(BATCH_CUTOFF)), ("b2", lambda r: r["extracted_at"] > iso(BATCH_CUTOFF))):
            path = out / "sources" / f"{system.lower()}_{batch}.jsonl.gz"
            chosen = [row for row in rows if keep(row)]
            data = "".join(canonical_json(row) + "\n" for row in chosen).encode("utf-8")
            with gzip.GzipFile(path, "wb", mtime=0) as handle:
                handle.write(data)
            files[path.name] = {"rows": len(chosen), "sha256": hashlib.sha256(data).hexdigest()}
    gov = governance(world)
    (out / "governance.json").write_text(canonical_json(gov), encoding="utf-8")
    (out / "sim_truth.json").write_text(canonical_json({"truth": truth(world), "defects": projector.defects}), encoding="utf-8")
    manifest = {"contract": CONTRACT, "generator_version": GENERATOR_VERSION, "batch_cutoff": iso(BATCH_CUTOFF), "files": files,
                "governance_sha256": sha256_canonical(gov), "defects": len(projector.defects),
                "defect_kinds": dict(sorted(_count(d["kind"] for d in projector.defects).items())), "sim_end": d(END)}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _count(values) -> dict:
    out: dict = defaultdict(int)
    for value in values:
        out[value] += 1
    return dict(out)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(write(root / "data" / "generated" / "world"), indent=2))
