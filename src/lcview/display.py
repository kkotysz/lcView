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


def frequency_text(frequency: float | None) -> str:
    return sig_text(frequency, 2)


def period_text_from_frequency(frequency: float | None) -> str:
    if frequency is None:
        return ""
    try:
        number = float(frequency)
    except (TypeError, ValueError):
        return ""
    if number <= 0 or not math.isfinite(number):
        return ""
    return sig_text(1.0 / number, 2)
