"""Formatting helpers for values shown to users."""

from __future__ import annotations

import math


def sig_text(value: float | None, digits: int = 2) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number):
        return ""
    return f"{number:.{digits}g}"


def fixed_text(value: float | None, decimals: int = 3) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number):
        return ""
    return f"{number:.{decimals}f}"


def frequency_text(frequency: float | None) -> str:
    return fixed_text(frequency)


def period_text_from_frequency(frequency: float | None) -> str:
    if frequency is None:
        return ""
    try:
        number = float(frequency)
    except (TypeError, ValueError):
        return ""
    if number <= 0 or not math.isfinite(number):
        return ""
    return fixed_text(1.0 / number)
