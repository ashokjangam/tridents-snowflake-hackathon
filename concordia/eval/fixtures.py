"""Load frozen fixtures. Expanding a date range is not a metric formula."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "golden_v1.json"


def load_golden() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def prepare(case: dict) -> dict:
    prepared = json.loads(json.dumps(case))
    rows = list(prepared.get("demand", []))
    for block in prepared.get("demand_ranges", []):
        day = date.fromisoformat(block["start"])
        end = date.fromisoformat(block["end"])
        while day <= end:
            rows.append(
                {
                    "on": day.isoformat(),
                    "qty": block["qty"],
                    "item_id": block["item_id"],
                    "facility_id": block["facility_id"],
                    "inventory_class": block["inventory_class"],
                }
            )
            day += timedelta(days=1)
    prepared["demand"] = rows
    return prepared
