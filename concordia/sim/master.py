"""Meridian Motion master data for CONCORDIA_SIM_V1.

Fictional organisations only. Distributions are design assumptions, not
empirical estimates.
"""

from __future__ import annotations

from sim.world import FACILITIES, POPULATION

GEOGRAPHIES = (
    {"geography_id": "GEO-NORTHEAST", "name": "Northeast", "country": "US", "timezone": "America/New_York"},
    {"geography_id": "GEO-SOUTHEAST", "name": "Southeast", "country": "US", "timezone": "America/New_York"},
    {"geography_id": "GEO-MIDWEST", "name": "Midwest", "country": "US", "timezone": "America/Chicago"},
    {"geography_id": "GEO-WEST", "name": "West", "country": "US", "timezone": "America/Los_Angeles"},
    {"geography_id": "GEO-DACH", "name": "DACH", "country": "DE", "timezone": "Europe/Berlin"},
    {"geography_id": "GEO-BENELUX", "name": "Benelux", "country": "NL", "timezone": "Europe/Amsterdam"},
)

CALENDARS = (
    {"calendar_id": "CAL-WEEKDAY", "name": "Monday to Friday", "shutdowns": []},
    {"calendar_id": "CAL-DAYTON", "name": "Dayton plant", "shutdowns": ["2026-05-25"]},
)

FACILITY_CALENDAR = {"FAC-DAYTON": "CAL-DAYTON"}

CURRENCIES = ("USD", "EUR", "MXN", "CNY")

SUPPLIER_COUNTRIES = (
    ("US", "USD", 16),
    ("MX", "MXN", 8),
    ("DE", "EUR", 9),
    ("CN", "CNY", 7),
)

SUPPLIER_WORDS = (
    "Apex Bearings", "Northfield Castings", "Lumen Magnetics", "Cobalt Ridge Wire", "Halcyon Seals",
    "Ironvale Fasteners", "Brightwater Polymers", "Kestrel Electronics", "Summit Gearworks", "Pioneer Laminations",
    "Bluehaven Copper", "Orion Shafts", "Granite Peak Housings", "Silverline Connectors", "Redwood Encoders",
    "Atlas Thermal", "Vireo Coatings", "Monarch Springs", "Delta Fold Packaging", "Corsair Controls",
    "Sierra Magnet Works", "Trident Insulators", "Juniper Precision", "Falcon Brake Systems", "Westmark Alloys",
    "Harbor Ceramic", "Quill Sensors", "Ember Rotor", "Nimbus Cable", "Starling Optics",
    "Rheinwerk Lager", "Elbe Antriebsteile", "Taunus Gusstechnik", "Schwarzwald Dichtungen", "Bodensee Elektronik",
    "Pearl River Motors", "Jade Harbor Metals", "Lotus Bay Plastics", "Yangtze Coil", "Golden Gate Magnet",
)

CUSTOMER_NAMES = (
    "Harbor Point Automation", "Granite State Robotics", "Hudson Valley Packaging", "Beacon Hill Medical Devices",
    "Tidewater Conveyors", "Peachtree Fluid Systems", "Magnolia Food Equipment", "Coastal Palm Fabrication",
    "Lakeshore Machine Tools", "Prairie Wind Agritech", "Great Lakes Bottling", "Heartland Elevators",
    "Cascade Lift Systems", "Mojave Solar Trackers", "Pacific Rim Logistics", "Redwood Lab Automation",
    "Alpen Fördertechnik", "Isar Medizintechnik", "Main Verpackung", "Neckar Robotik",
    "Rotterdam Haven Systems", "Brabant Food Machines", "Utrecht Sorting", "Flanders Textile Works",
)

CUSTOMER_GEOGRAPHY = (
    ["GEO-NORTHEAST"] * 4 + ["GEO-SOUTHEAST"] * 4 + ["GEO-MIDWEST"] * 4 + ["GEO-WEST"] * 4
    + ["GEO-DACH"] * 4 + ["GEO-BENELUX"] * 4
)

FG_HOME = (["FAC-DAYTON"] * 15) + (["FAC-RENO"] * 13) + (["FAC-STUTTGART"] * 12)

COMPONENT_KINDS = (
    "Bearing", "Stator winding", "Rotor stack", "Housing", "Shaft", "Encoder", "Seal kit", "Fastener set",
    "Terminal box", "Cooling fan", "Brake module", "Magnet set", "Cable harness", "Insulation kit", "Gear set",
)

SA_KINDS = ("Rotor assembly", "Stator assembly", "Drive end shield", "Brake assembly", "Encoder module", "Gearhead")

SERVING = {
    "GEO-NORTHEAST": ("FAC-DAYTON", "DC-NEWARK"),
    "GEO-SOUTHEAST": ("FAC-DAYTON", "DC-NEWARK"),
    "GEO-MIDWEST": ("FAC-DAYTON", "DC-NEWARK"),
    "GEO-WEST": ("FAC-RENO", "DC-OAKLAND"),
    "GEO-DACH": ("FAC-STUTTGART", "DC-HAMBURG"),
    "GEO-BENELUX": ("FAC-STUTTGART", "DC-HAMBURG"),
}

PLANT_DC = {"FAC-DAYTON": "DC-NEWARK", "FAC-RENO": "DC-OAKLAND", "FAC-STUTTGART": "DC-HAMBURG"}


def facility(facility_id: str) -> dict:
    return next(row for row in FACILITIES if row["facility_id"] == facility_id)


def geography(geography_id: str) -> dict:
    return next(row for row in GEOGRAPHIES if row["geography_id"] == geography_id)


def build_master(rng) -> dict:
    """Deterministic master data from the `supply` stream."""
    assert len(SUPPLIER_WORDS) == POPULATION["suppliers"]
    assert len(CUSTOMER_NAMES) == POPULATION["customers"]

    suppliers = []
    currency_of = {country: currency for country, currency, _ in SUPPLIER_COUNTRIES}
    for index, name in enumerate(SUPPLIER_WORDS):
        if index >= 35:
            country = "CN"
        elif index >= 30:
            country = "DE"
        elif index == 0 or index % 3:
            country = "US"
        else:
            country = "MX"
        suppliers.append(
            {
                "supplier_id": f"SUP-{index + 1:03d}",
                "name": name,
                "country": country,
                "currency": currency_of[country],
                # A few operating companies roll up to a parent supplier, so the party hierarchy is exercised.
                "parent_supplier_id": f"SUP-{index:03d}" if index in (5, 15, 25, 35) else None,
                "reliability": float(rng.uniform(0.82, 0.98)) if index else 0.9,
                "tier": "DOMESTIC" if country == "US" else ("NEARSHORE" if country == "MX" else "OVERSEAS"),
            }
        )

    items = []
    for number in range(401, 441):
        fid = f"MM-{number}"
        items.append(
            {
                "item_id": fid,
                "name": f"Meridian servo motor {fid}",
                "item_type": "FINISHED",
                "family": f"MM-{str(number)[:2]}x",
                "home_facility_id": "FAC-DAYTON" if fid == "MM-440" else FG_HOME[number - 401],
                "unit_weight_kg": round(float(rng.uniform(4, 22)), 1),
                "price_usd_cents": int(rng.integers(32000, 98000)),
                "purchased": fid == "MM-440",
            }
        )
    for number in range(201, 237):
        items.append(
            {
                "item_id": f"SA-{number}",
                "name": f"{SA_KINDS[number % len(SA_KINDS)]} SA-{number}",
                "item_type": "SUBASSEMBLY",
                "family": "SA",
                "home_facility_id": ("FAC-DAYTON", "FAC-RENO", "FAC-STUTTGART")[number % 3],
                "unit_weight_kg": round(float(rng.uniform(1, 6)), 1),
                "price_usd_cents": 0,
                "purchased": False,
            }
        )
    for number in range(1001, 1125):
        items.append(
            {
                "item_id": f"CP-{number}",
                "name": f"{COMPONENT_KINDS[number % len(COMPONENT_KINDS)]} CP-{number}",
                "item_type": "COMPONENT",
                "family": COMPONENT_KINDS[number % len(COMPONENT_KINDS)],
                "home_facility_id": None,
                "unit_weight_kg": round(float(rng.uniform(0.05, 3.0)), 2),
                "price_usd_cents": int(rng.integers(150, 6500)),
                "purchased": True,
            }
        )
    assert len(items) == POPULATION["parts"]

    by_id = {item["item_id"]: item for item in items}
    components = [item for item in items if item["item_type"] == "COMPONENT"]
    subassemblies = [item for item in items if item["item_type"] == "SUBASSEMBLY"]

    bom = []
    parents = [item for item in items if item["item_type"] in ("FINISHED", "SUBASSEMBLY") and not item["purchased"]]
    assert len(parents) == POPULATION["bom_parents"]
    for parent in parents:
        if parent["item_type"] == "FINISHED":
            same_plant = [sa for sa in subassemblies if sa["home_facility_id"] == parent["home_facility_id"]]
            picks = list(rng.choice(len(same_plant), size=2, replace=False))
            lines = [(same_plant[int(i)]["item_id"], 1) for i in picks]
            comp_picks = rng.choice(len(components), size=int(rng.integers(2, 5)), replace=False)
            lines += [(components[int(i)]["item_id"], int(rng.integers(1, 5))) for i in comp_picks]
        else:
            comp_picks = rng.choice(len(components), size=int(rng.integers(2, 5)), replace=False)
            lines = [(components[int(i)]["item_id"], int(rng.integers(1, 7))) for i in comp_picks]
        for component_id, per in lines:
            bom.append(
                {
                    "parent_id": parent["item_id"],
                    "component_id": component_id,
                    "qty_per": per,
                    "revision": "A",
                    "effective_from": "2025-01-01",
                    "effective_to": None,
                }
            )
    # BOM revision/effectivity scenario: twelve parents swap one component.
    substitutions = []
    revised = rng.choice(len(parents), size=12, replace=False)
    for offset, index in enumerate(revised):
        parent = parents[int(index)]
        rows = [row for row in bom if row["parent_id"] == parent["item_id"] and row["component_id"].startswith("CP-")]
        if not rows:
            continue
        old = rows[0]
        switch = "2025-09-01" if offset % 2 else "2026-03-02"
        used = {row["component_id"] for row in bom if row["parent_id"] == parent["item_id"]}
        candidates = [c["item_id"] for c in components if c["item_id"] not in used]
        new_component = candidates[int(rng.integers(0, len(candidates)))]
        substitutions.append(
            {
                "item_id": old["component_id"],
                "substitute_item_id": new_component,
                "valid_from": switch,
                "valid_to": None,
                "approved_by": "CONCORDIA_CHANGE_BOARD",
            }
        )
        old["effective_to"] = switch
        for row in [row for row in bom if row["parent_id"] == parent["item_id"] and row is not old]:
            if row["effective_to"] is None and row["revision"] == "A":
                bom.append({**row, "revision": "B", "effective_from": switch})
                row["effective_to"] = switch
        bom.append(
            {
                "parent_id": parent["item_id"],
                "component_id": new_component,
                "qty_per": old["qty_per"],
                "revision": "B",
                "effective_from": switch,
                "effective_to": None,
            }
        )

    # Component sourcing: one primary supplier per component; plants that consume it.
    supply = []
    domestic = [s for s in suppliers if s["country"] == "US"]
    for index, component in enumerate(components):
        if component["item_id"] == "CP-1001":
            supplier = suppliers[0]
        else:
            supplier = suppliers[1 + (index * 7) % (len(suppliers) - 1)]
        if index % 9 == 0 and supplier["country"] != "US":
            supplier = domestic[index % len(domestic)]
        supply.append({"supplier_id": supplier["supplier_id"], "item_id": component["item_id"]})
    supply.append({"supplier_id": "SUP-001", "item_id": "MM-440"})

    customers = []
    for index, name in enumerate(CUSTOMER_NAMES):
        cid = f"CUS-{index + 1:03d}"
        geo = CUSTOMER_GEOGRAPHY[index]
        ship_tos = []
        for site in range(1 + (index % 3 == 0)):
            ship_tos.append(
                {
                    "ship_to_id": f"{cid}-ST{site + 1}",
                    "customer_id": cid,
                    "geography_id": geo,
                    "timezone": geography(geo)["timezone"],
                    "calendar_id": "CAL-WEEKDAY",
                    "country": geography(geo)["country"],
                }
            )
        fg = [item for item in items if item["item_type"] == "FINISHED"]
        affinity = sorted(int(i) for i in rng.choice(len(fg), size=8, replace=False))
        customers.append(
            {
                "customer_id": cid,
                "name": name,
                "geography_id": geo,
                "ship_tos": ship_tos,
                "items": [fg[i]["item_id"] for i in affinity],
                "weekly_rate": float(rng.uniform(0.18, 0.42)),
                "parent_customer_id": None,
            }
        )
    # CRM merged two accounts; ERP still carries both.
    customers[11]["parent_customer_id"] = customers[10]["customer_id"]
    # Hero customers order MM-440.
    for index in (0, 1, 2):
        if "MM-440" not in customers[index]["items"]:
            customers[index]["items"][0] = "MM-440"

    lanes = []
    for facility_row in FACILITIES:
        for geo in GEOGRAPHIES:
            same_country = facility_row["country"] == geo["country"] or {facility_row["country"], geo["country"]} <= {"DE", "NL"}
            base = 2.0 if same_country else 9.0
            lanes.append(
                {
                    "lane_id": f"LN-{facility_row['facility_id']}-{geo['geography_id']}",
                    "origin_id": facility_row["facility_id"],
                    "destination_id": geo["geography_id"],
                    "mode": "TRUCK" if same_country else "OCEAN",
                    "transit_mu": base,
                    "carrier": ("Northline Freight", "Atlas Carriers", "Rhein Spedition")[len(lanes) % 3],
                }
            )
    for plant, dc in PLANT_DC.items():
        lanes.append({"lane_id": f"LN-{plant}-{dc}", "origin_id": plant, "destination_id": dc, "mode": "TRUCK", "transit_mu": 2.0, "carrier": "Northline Freight"})
    for origin in ("US", "MX", "DE", "CN"):
        for plant in ("FAC-DAYTON", "FAC-RENO", "FAC-STUTTGART"):
            lanes.append(
                {
                    "lane_id": f"LN-{origin}-{plant}",
                    "origin_id": f"COUNTRY-{origin}",
                    "destination_id": plant,
                    "mode": "TRUCK" if origin in ("US", "MX") and plant != "FAC-STUTTGART" else "OCEAN",
                    "transit_mu": 3.0,
                    "carrier": "Atlas Carriers",
                }
            )
    for origin in ("US", "MX", "DE"):
        for dc in ("DC-NEWARK", "DC-OAKLAND", "DC-HAMBURG"):
            lanes.append(
                {
                    "lane_id": f"LN-{origin}-{dc}",
                    "origin_id": f"COUNTRY-{origin}",
                    "destination_id": dc,
                    "mode": "TRUCK",
                    "transit_mu": 3.0,
                    "carrier": "Atlas Carriers",
                }
            )
    assert len(lanes) == POPULATION["lanes"], len(lanes)
    return {
        "suppliers": suppliers,
        "items": items,
        "items_by_id": by_id,
        "bom": bom,
        "substitutions": substitutions,
        "supply": supply,
        "customers": customers,
        "lanes": lanes,
    }
