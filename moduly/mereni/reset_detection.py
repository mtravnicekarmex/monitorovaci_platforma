from __future__ import annotations

import math


RESET_NEGATIVE_DIFF_THRESHOLD = 0.001
RESET_NEGATIVE_DIFF_ROUND_DECIMALS = 6


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def has_significant_negative_diff(
    current_value: object,
    previous_value: object,
    *,
    threshold: float = RESET_NEGATIVE_DIFF_THRESHOLD,
) -> bool:
    current_number = _to_float(current_value)
    previous_number = _to_float(previous_value)
    if current_number is None or previous_number is None:
        return False
    difference = round(current_number - previous_number, RESET_NEGATIVE_DIFF_ROUND_DECIMALS)
    return difference < -threshold
