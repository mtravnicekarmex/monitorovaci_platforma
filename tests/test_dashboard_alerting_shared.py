import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard.alerting_shared import (
    ALERTING_MODULE_OPTIONS,
    get_alerting_module_config,
)


def test_alerting_shared_supports_vodomery_and_plynomery_modules():
    assert ALERTING_MODULE_OPTIONS == ("vodomery", "plynomery")


def test_vodomery_alerting_config_contains_zero_flow_and_expected_zero():
    config = get_alerting_module_config("vodomery")

    assert "ZERO_FLOW" in config.event_type_options
    assert config.expected_zero is not None
    assert config.expected_zero.select_label == "Vodomery s ocekavanym nulovym odberem"


def test_plynomery_alerting_config_contains_long_high_usage_and_expected_zero():
    config = get_alerting_module_config("plynomery")

    assert "LONG_HIGH_USAGE" in config.event_type_options
    assert config.expected_zero is not None
    assert config.expected_zero.select_label == "Plynomery s ocekavanym nulovym odberem"
