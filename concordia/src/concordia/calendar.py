"""Governed facility calendars. A missing calendar is not guessed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Calendar:
    calendar_id: str
    shutdowns: frozenset[date]

    def is_business_day(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self.shutdowns


def calendar_from(raw: dict | None) -> Calendar | None:
    if not raw or not raw.get("id"):
        return None
    shutdowns = frozenset(date.fromisoformat(day) for day in raw.get("shutdowns", []))
    return Calendar(raw["id"], shutdowns)


def add_business_days(start: date, days: int, governed: Calendar) -> date:
    if days < 0:
        raise ValueError("business-day offset cannot be negative")
    current = start
    remaining = days
    while remaining:
        current += timedelta(days=1)
        if governed.is_business_day(current):
            remaining -= 1
    return current


def parse_utc(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("naive timestamps are not interpreted")
    return parsed.astimezone(timezone.utc)


def local_date(moment: datetime, zone: str) -> date:
    if moment.tzinfo is None:
        raise ValueError("naive timestamps are not interpreted")
    return moment.astimezone(ZoneInfo(zone)).date()
