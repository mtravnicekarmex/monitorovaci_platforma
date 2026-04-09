from __future__ import annotations

import math


def calculate_percentage_deviation(actual_value: object, expected_value: object) -> float | None:
    try:
        actual_numeric = float(actual_value)
        expected_numeric = float(expected_value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(actual_numeric) or not math.isfinite(expected_numeric):
        return None

    if abs(expected_numeric) < 0.0005:
        return 0.0 if abs(actual_numeric) < 0.0005 else None

    deviation_percent = ((actual_numeric - expected_numeric) / expected_numeric) * 100
    if abs(deviation_percent) < 0.05:
        deviation_percent = 0.0
    return round(deviation_percent, 1)
