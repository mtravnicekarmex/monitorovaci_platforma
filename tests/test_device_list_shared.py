import datetime
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard import device_list_shared
from moduly.mereni.elektromery.database.models import Elektromer_areal_Zarizeni
from moduly.mereni.manometry.database.models import Manometr_areal_Zarizeni


def test_build_create_fields_skips_auto_primary_key():
    fields = device_list_shared.build_create_fields(device_list_shared.DEVICE_LIST_CONFIGS["manometry"])
    field_attrs = [field.attr for field in fields]

    assert "id" not in field_attrs
    assert "seriove_cislo" in field_attrs
    assert next(field for field in fields if field.attr == "seriove_cislo").required is True


def test_build_edit_fields_skips_primary_key():
    vodomery_fields = device_list_shared.build_edit_fields(device_list_shared.DEVICE_LIST_CONFIGS["vodomery"])
    manometry_fields = device_list_shared.build_edit_fields(device_list_shared.DEVICE_LIST_CONFIGS["manometry"])

    assert "identifikace" not in [field.attr for field in vodomery_fields]
    assert "id" not in [field.attr for field in manometry_fields]
    assert "seriove_cislo" in [field.attr for field in manometry_fields]


def test_primary_key_attr_requires_single_primary_key():
    assert device_list_shared._primary_key_attr(Elektromer_areal_Zarizeni) == "identifikace"
    assert device_list_shared._primary_key_attr(Manometr_areal_Zarizeni) == "id"


def test_coerce_form_value_parses_bigint_and_datetime():
    assert device_list_shared._coerce_form_value(Elektromer_areal_Zarizeni, "EAN", "859 123") == 859123
    assert device_list_shared._coerce_form_value(
        Elektromer_areal_Zarizeni,
        "platnost_od",
        "20.05.2026 13:45",
    ) == datetime.datetime(2026, 5, 20, 13, 45)


def test_coerce_form_value_rejects_invalid_required_value():
    with pytest.raises(ValueError, match="povinné"):
        device_list_shared._coerce_form_value(Manometr_areal_Zarizeni, "seriove_cislo", "")


def test_create_device_record_requires_admin():
    with pytest.raises(PermissionError):
        device_list_shared.create_device_record("vodomery", {}, user_is_admin=False)


def test_update_device_record_requires_admin():
    with pytest.raises(PermissionError):
        device_list_shared.update_device_record("vodomery", "V-1", {}, user_is_admin=False)
