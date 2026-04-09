from app.metrics_utils import calculate_percentage_deviation


def test_calculate_percentage_deviation_returns_positive_value_for_higher_actual():
    assert calculate_percentage_deviation(12, 10) == 20.0


def test_calculate_percentage_deviation_returns_negative_value_for_lower_actual():
    assert calculate_percentage_deviation(8, 10) == -20.0


def test_calculate_percentage_deviation_returns_zero_for_matching_zero_values():
    assert calculate_percentage_deviation(0, 0) == 0.0


def test_calculate_percentage_deviation_returns_none_for_nonzero_actual_with_zero_expected():
    assert calculate_percentage_deviation(3, 0) is None


def test_calculate_percentage_deviation_returns_none_for_invalid_input():
    assert calculate_percentage_deviation("x", 10) is None
