"""Frozen population and facility identity. Not a metric formula."""

POPULATION = {
    "plants": 3,
    "distribution_centres": 3,
    "suppliers": 40,
    "parts": 200,
    "bom_parents": 75,
    "customers": 24,
    "lanes": 60,
}

FACILITIES = (
    {"facility_id": "FAC-DAYTON", "name": "Dayton", "kind": "PLANT", "country": "US", "timezone": "America/New_York"},
    {"facility_id": "FAC-RENO", "name": "Reno", "kind": "PLANT", "country": "US", "timezone": "America/Los_Angeles"},
    {"facility_id": "FAC-STUTTGART", "name": "Stuttgart", "kind": "PLANT", "country": "DE", "timezone": "Europe/Berlin"},
    {"facility_id": "DC-NEWARK", "name": "Newark", "kind": "DC", "country": "US", "timezone": "America/New_York"},
    {"facility_id": "DC-OAKLAND", "name": "Oakland", "kind": "DC", "country": "US", "timezone": "America/Los_Angeles"},
    {"facility_id": "DC-HAMBURG", "name": "Hamburg", "kind": "DC", "country": "DE", "timezone": "Europe/Berlin"},
)

HERO = {
    "item_id": "MM-440",
    "supplier": "Apex Bearings",
    "supplier_country": "US",
    "plant_id": "FAC-DAYTON",
    "receipt_incoterm": "EXW",
    "sales_incoterm": "DAP",
    "period": ["2026-05-01", "2026-05-31"],
    "early_as_of": "2026-06-05T23:59:59Z",
    "final_as_of": "2026-07-15T23:59:59Z",
    "dayton_shutdown": "2026-05-25",
}

STREAMS = (
    "demand",
    "supply",
    "production",
    "quality",
    "transit",
    "commercial",
    "feedback",
    "defects",
)
