import sys
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.elektromery.SOFTLINK import SOFTLINK_data_zarizeni


class _FakeClickable:
    def __init__(self, *, timeout_error: bool = False):
        self.timeout_error = timeout_error
        self.click_calls = 0

    def click(self, timeout: int) -> None:
        self.click_calls += 1
        if self.timeout_error:
            raise PlaywrightTimeoutError("timeout")


class _FakeLinkLocator:
    def __init__(self, clickable: _FakeClickable):
        self.first = clickable


class _FakePage:
    def __init__(self):
        self.cz_link = _FakeClickable(timeout_error=True)
        self.en_link = _FakeClickable()
        self.any_link = _FakeClickable()

    def get_by_role(self, role: str, *, name: str):
        assert role == "link"
        if name == "Vstoupit do portálu":
            return self.cz_link
        if name == "Enter":
            return self.en_link
        raise AssertionError(f"Unexpected role lookup: {role=} {name=}")

    def locator(self, selector: str):
        assert selector == "a"
        return _FakeLinkLocator(self.any_link)


class _FakePortal:
    def __init__(self):
        self.wait_calls: list[int] = []

    def wait_for_timeout(self, timeout_ms: int) -> None:
        self.wait_calls.append(timeout_ms)


class _FakeResponse:
    def __init__(self, status, data):
        self.status = status
        self._data = data

    def json(self):
        return self._data


class _FakeRequest:
    def __init__(self, response=None):
        self.response = response
        self.calls = []

    def post(self, url, *, headers, data):
        self.calls.append({"url": url, "headers": headers, "data": data})
        return self.response


class _FakeContext:
    def __init__(self, response=None):
        self.request = _FakeRequest(response)
        self.pages = [_FakePortal()]


def test_run_playwright_action_fallbacks_uses_next_action_after_timeout():
    calls: list[str] = []

    def first_action():
        calls.append("first")
        raise PlaywrightTimeoutError("timeout")

    def second_action():
        calls.append("second")
        return "ok"

    result = SOFTLINK_data_zarizeni._run_playwright_action_fallbacks((first_action, second_action))

    assert result == "ok"
    assert calls == ["first", "second"]


def test_click_portal_entry_falls_back_to_enter_link():
    page = _FakePage()

    SOFTLINK_data_zarizeni._click_portal_entry(page, 1000)

    assert page.cz_link.click_calls == 1
    assert page.en_link.click_calls == 1
    assert page.any_link.click_calls == 0


def test_fetch_devices_uses_playwright_request_context():
    context = _FakeContext(_FakeResponse(200, [{"me_id": 101}]))
    request_window = SOFTLINK_data_zarizeni._SoftlinkRequestWindow(date_from_ms=10, date_to_ms=20)

    response = SOFTLINK_data_zarizeni._fetch_devices_with_request_context(context, request_window)

    assert response == {"status": 200, "data": [{"me_id": 101}]}
    assert context.request.calls == [
        {
            "url": "https://cem2.softlink.cz/cemapi/api?id=46",
            "headers": {"Content-Type": "application/json"},
            "data": {"mit_id": 105, "od": 10, "do": 20, "typ": "DEN"},
        }
    ]


def test_fetch_devices_adds_authorization_header_when_token_is_supplied():
    context = _FakeContext(_FakeResponse(200, []))
    request_window = SOFTLINK_data_zarizeni._SoftlinkRequestWindow(date_from_ms=10, date_to_ms=20)

    response = SOFTLINK_data_zarizeni._fetch_devices_with_request_context(
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
    token = SOFTLINK_data_zarizeni._extract_auth_token_from_storage_state(
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


def test_wait_for_authenticated_device_fetch_retries_until_valid_response(monkeypatch):
    context = _FakeContext()
    responses = [
        {"status": 401, "data": {"message": "unauthorized"}},
        {"status": 200, "data": [{"me_id": 101}]},
    ]

    monkeypatch.setattr(
        SOFTLINK_data_zarizeni,
        "_fetch_devices_with_request_context",
        lambda current_context, request_window, auth_token=None: responses.pop(0),
    )

    response = SOFTLINK_data_zarizeni._wait_for_authenticated_device_fetch(
        context,
        SOFTLINK_data_zarizeni._SoftlinkRequestWindow(date_from_ms=0, date_to_ms=1),
        timeout_ms=2000,
    )

    assert response == {"status": 200, "data": [{"me_id": 101}]}
    assert context.pages[0].wait_calls == [1000]


def test_invalid_device_response_reports_auth_error():
    with pytest.raises(
        SOFTLINK_data_zarizeni.SoftlinkDeviceAuthError,
        match="neautorizovany",
    ):
        SOFTLINK_data_zarizeni._raise_for_invalid_device_response(
            {"status": 401, "data": {"message": "unauthorized"}}
        )
