import datetime
from decimal import Decimal

from moduly.apps.dashboard import api_client


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_create_admin_revize_serializes_dates_and_decimals(monkeypatch):
    captured = {}

    def fake_request(method, path, **kwargs):
        captured.update(
            method=method,
            path=path,
            access_token=kwargs["access_token"],
            json_payload=kwargs["json_payload"],
        )
        return _Response({"id": 7})

    monkeypatch.setattr(api_client, "_request", fake_request)

    revize_id = api_client.create_admin_revize(
        "token",
        {
            "budova": "F",
            "datum": datetime.date(2026, 6, 14),
            "delka_platnosti": Decimal("12"),
            "typ_zarizeni": "HYDRANTY",
        },
        [10, 11],
    )

    assert revize_id == 7
    assert captured == {
        "method": "POST",
        "path": "/api/v1/admin/revize",
        "access_token": "token",
        "json_payload": {
            "budova": "F",
            "datum": "2026-06-14",
            "delka_platnosti": 12,
            "typ_zarizeni": "HYDRANTY",
            "linked_device_ids": [10, 11],
        },
    }


def test_update_admin_device_uses_admin_endpoint(monkeypatch):
    captured = {}

    def fake_request(method, path, **kwargs):
        captured.update(
            method=method,
            path=path,
            access_token=kwargs["access_token"],
            json_payload=kwargs["json_payload"],
        )
        return _Response({})

    monkeypatch.setattr(api_client, "_request", fake_request)

    api_client.update_admin_device(
        "token",
        "manometry",
        42,
        {"seriove_cislo": "M-42"},
    )

    assert captured == {
        "method": "PATCH",
        "path": "/api/v1/admin/devices/manometry",
        "access_token": "token",
        "json_payload": {
            "primary_key_value": 42,
            "fields": {"seriove_cislo": "M-42"},
        },
    }
