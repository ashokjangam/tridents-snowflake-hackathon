"""Integer cents and six-place quantities. Half-even."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN

QTY = Decimal("0.000001")
FOUR = Decimal("0.0001")
CENT = Decimal("1")


def D(value: object) -> Decimal:
    return Decimal(str(value))


def qty(value: object) -> Decimal:
    return D(value).quantize(QTY, rounding=ROUND_HALF_EVEN)


def qty_str(value: Decimal) -> str:
    return format(value.quantize(QTY, rounding=ROUND_HALF_EVEN), "f")


def display_str(value: Decimal) -> str:
    return format(value.quantize(FOUR, rounding=ROUND_HALF_EVEN), "f")


def to_usd_cents(amount_minor: int, fx_rate: object) -> int:
    raw = Decimal(amount_minor) * D(fx_rate)
    return int(raw.quantize(CENT, rounding=ROUND_HALF_EVEN))


def allocate_cents(total: int, weights: list[Decimal]) -> list[int]:
    if total < 0:
        raise ValueError("allocation total cannot be negative")
    weight_sum = sum(weights, Decimal("0"))
    if weight_sum <= 0:
        raise ValueError("allocation weights must be positive")
    raw = [Decimal(total) * weight / weight_sum for weight in weights]
    rounded = [int(item.to_integral_value(ROUND_HALF_EVEN)) for item in raw]
    drift = total - sum(rounded)
    if drift != 0:
        step = 1 if drift > 0 else -1
        ranked = sorted(
            range(len(raw)),
            key=lambda index: (raw[index] - Decimal(rounded[index]), -index),
            reverse=drift > 0,
        )
        for offset in range(abs(drift)):
            rounded[ranked[offset % len(ranked)]] += step
    if sum(rounded) != total:
        raise RuntimeError("allocation did not reconcile to the invoice total")
    return rounded
