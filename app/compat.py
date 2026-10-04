"""Small compatibility helpers shared by Python 3.10+ runtimes."""

from __future__ import annotations

from typing import NoReturn


def assert_never(value: NoReturn) -> NoReturn:
    """Fail loudly when an enum/union variant was not handled."""
    raise AssertionError(f"Unhandled value: {value!r}")
