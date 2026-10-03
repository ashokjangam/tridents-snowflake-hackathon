"""Governed unit conversions. A missing factor is unresolved, not guessed."""

from __future__ import annotations

from decimal import Decimal

from concordia.money import qty

# Base-unit factors published with the contract. This is not a general converter.
FACTORS: dict[tuple[str, str], Decimal] = {
    ("CASE", "EA"): Decimal("12"),
    ("KG", "G"): Decimal("1000"),
}


def to_base(quantity: object, source_uom: str, base_uom: str) -> Decimal | None:
    amount = qty(quantity)
    if source_uom == base_uom:
        return amount
    factor = FACTORS.get((source_uom, base_uom))
    if factor is None:
        return None
    return qty(amount * factor)
