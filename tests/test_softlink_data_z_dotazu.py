import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.elektromery.SOFTLINK import SOFTLINK_data_z_dotazu


class _FakeResponse:
    def __init__(self, status, data):
        self.status = status
        self._data = data

    def json(self):
        return self._data


class _FakeRequest:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, *, headers, data):
        self.calls.append({"url": url, "headers": headers, "data": data})
        return self.response


class _FakePage:
    def __init__(self):
        self.wait_calls = []

    def wait_for_timeout(self, timeout_ms):
        self.wait_calls.append(timeout_ms)


class _FakeContext:
    def __init__(self, response=None):
        self.request = _FakeRequest(response)
        self.pages = [_FakePage()]


def test_fetch_measurements_uses_playwright_request_context():
    context = _FakeContext(_FakeResponse(200, [{"me_id": 101}]))
    request_window = SOFTLINK_data_z_dotazu._SoftlinkRequestWindow(date_from_ms=10, date_to_ms=20)

    response = SOFTLINK_data_z_dotazu._fetch_measurements_with_request_context(context, request_window)

    assert response == {"status": 200, "data": [{"me_id": 101}]}
    assert context.request.calls == [
        {
            "url": "https://cem2.softlink.cz/cemapi/api?id=45",
            "headers": {"Content-Type": "application/json"},
            "data": {"mit_id": 105, "od": 10, "do": 20, "typ": "DEN"},
        }
    ]


def test_fetch_measurements_adds_authorization_header_when_token_is_supplied():
    context = _FakeContext(_FakeResponse(200, []))
    request_window = SOFTLINK_data_z_dotazu._SoftlinkRequestWindow(date_from_ms=10, date_to_ms=20)

    response = SOFTLINK_data_z_dotazu._fetch_measurements_with_request_context(
        context,
        request_window,
        auth_token="token-value",
    )

    assert response == {"status": 200, "data": []}
    assert context.request.calls[0]["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer token-value",
    }


def test_extract_auth_token_from_storage_state_reads_cem_lds_auth():
    token = SOFTLINK_data_z_dotazu._extract_auth_token_from_storage_state(
        {
            "origins": [
                {
                    "origin": "https://ldsportal.softlink.cz",
                    "localStorage": [
                        {
                            "name": "cem_lds_auth",
                            "value": '{"access_token":"token-value","refresh_token":"refresh"}',
                        }
                    ],
                }
            ]
        }
    )

    assert token == "token-value"


def test_wait_for_authenticated_measurements_fetch_retries_until_valid(monkeypatch):
    context = _FakeContext()
    responses = [
        {"status": 401, "data": {"message": "unauthorized"}},
        {"status": 200, "data": [{"me_id": 101}]},
    ]

    monkeypatch.setattr(
        SOFTLINK_data_z_dotazu,
        "_fetch_measurements_with_request_context",
        lambda current_context, request_window, auth_token=None: responses.pop(0),
    )

    response = SOFTLINK_data_z_dotazu._wait_for_authenticated_measurements_fetch(
        context,
        SOFTLINK_data_z_dotazu._SoftlinkRequestWindow(date_from_ms=0, date_to_ms=1),
        timeout_ms=2000,
    )

    assert response == {"status": 200, "data": [{"me_id": 101}]}
    assert context.pages[0].wait_calls == [1000]


def test_invalid_measurements_response_reports_auth_error():
    with pytest.raises(
        SOFTLINK_data_z_dotazu.SoftlinkMeasurementAuthError,
        match="neautorizovany",
    ):
        SOFTLINK_data_z_dotazu._raise_for_invalid_measurements_response(
            {"status": 401, "data": {"message": "unauthorized"}}
        )
