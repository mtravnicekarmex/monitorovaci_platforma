import datetime
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.smartfuelpass import service


class FakeElement:
    def __init__(self):
        self.cleared = False
        self.values = []

    def clear(self):
        self.cleared = True

    def send_keys(self, value):
        self.values.append(value)


class FakeDriver:
    def __init__(self):
        self.visited_urls = []
        self.current_url = ""
        self.inputs = {
            "Email": FakeElement(),
            "Password": FakeElement(),
        }
        self.cookies = [
            {
                "name": "sessionid",
                "value": "abc123",
                "domain": "portal.smartfuelpass.com",
                "path": "/",
            }
        ]
        self.quit_called = False

    def get(self, url):
        self.visited_urls.append(url)
        self.current_url = url

    def find_element(self, by, value):
        assert by == "id"
        return self.inputs[value]

    def get_cookies(self):
        return self.cookies

    def quit(self):
        self.quit_called = True


class FakePage:
    def __init__(self, *, url="https://portal.smartfuelpass.com/User/Login", html="<form id='loginForm'></form>"):
        self.url = url
        self._html = html

    def content(self):
        return self._html


class FakeReportingPage:
    def __init__(self, responses):
        self.responses = responses
        self.url = "about:blank"
        self._html = ""
        self.default_timeout = None
        self.visited_urls = []

    def set_default_timeout(self, timeout):
        self.default_timeout = timeout

    def goto(self, url, wait_until=None):
        self.visited_urls.append((url, wait_until))
        self.url = url
        self._html = self.responses[url]

    def wait_for_load_state(self, state, timeout=None):
        return None

    def content(self):
        return self._html


class FakeReportingContext:
    def __init__(self, page):
        self.page = page
        self.closed = False

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True


class FakeReportingBrowser:
    def __init__(self, context):
        self.context = context
        self.closed = False

    def new_context(self):
        return self.context

    def close(self):
        self.closed = True


class FakeReportingPlaywright:
    def __init__(self, browser, captured):
        self.browser = browser
        self.captured = captured
        self.chromium = self

    def launch(self, headless=True):
        self.captured["headless"] = headless
        return self.browser


class FakeReportingSyncPlaywright:
    def __init__(self, manager):
        self.manager = manager

    def __enter__(self):
        return self.manager

    def __exit__(self, exc_type, exc, tb):
        return False


def install_fake_reporting_playwright(monkeypatch, responses):
    captured = {}
    page = FakeReportingPage(responses)
    context = FakeReportingContext(page)
    browser = FakeReportingBrowser(context)
    manager = FakeReportingPlaywright(browser, captured)
    monkeypatch.setattr(
        service,
        "_load_playwright_api",
        lambda: (lambda: FakeReportingSyncPlaywright(manager), RuntimeError),
    )
    return captured, page, context, browser


def test_parse_report_targets_supports_labels_and_relative_urls(monkeypatch):
    monkeypatch.setattr(service, "_smartfuel_base_url", lambda: "https://portal.smartfuelpass.com/")

    targets = service.parse_report_targets(
        "overview=/Payment/MyProfile\nbilling=https://example.com/billing\n/AdHocChargingList"
    )

    assert [(target.key, target.url) for target in targets] == [
        ("overview", "https://portal.smartfuelpass.com/Payment/MyProfile"),
        ("billing", "https://example.com/billing"),
        ("adhoccharginglist", "https://portal.smartfuelpass.com/AdHocChargingList"),
    ]


def test_parse_report_targets_keeps_urls_with_query_parameters(monkeypatch):
    monkeypatch.setattr(service, "_smartfuel_base_url", lambda: "https://portal.smartfuelpass.com/")

    targets = service.parse_report_targets("https://portal.smartfuelpass.com/Report/List?filter=active")

    assert [(target.key, target.url) for target in targets] == [
        ("report_list", "https://portal.smartfuelpass.com/Report/List?filter=active"),
    ]


def test_weekly_report_recipients_require_explicit_configuration(monkeypatch):
    monkeypatch.setattr(service, "config", lambda key, default="": default)

    with pytest.raises(service.SmartFuelPassError, match="SMARTFUELPASS_WEEKLY_REPORT_RECIPIENTS"):
        service._smartfuel_weekly_report_recipients()


def test_fetch_reporting_snapshots_extracts_title_and_text(monkeypatch):
    target = service.SmartFuelPassReportTarget(
        key="dashboard",
        url="https://portal.smartfuelpass.com/dashboard",
    )
    login_calls = []
    captured, page, context, browser = install_fake_reporting_playwright(
        monkeypatch,
        {
            target.url: """
                <html>
                    <head><title>Dashboard - Smart Fuel Pass</title></head>
                    <body>
                        <script>hidden()</script>
                        <h1>Vehicles</h1>
                        <p>Monthly overview</p>
                    </body>
                </html>
                """,
        },
    )

    monkeypatch.setattr(
        service,
        "perform_playwright_login",
        lambda page, **kwargs: login_calls.append((page, kwargs)) or "https://portal.smartfuelpass.com/",
    )

    snapshots = service.fetch_reporting_snapshots(targets=(target,))

    assert len(snapshots) == 1
    assert snapshots[0].title == "Dashboard - Smart Fuel Pass"
    assert "Vehicles" in snapshots[0].text
    assert "hidden()" not in snapshots[0].text
    assert login_calls[0][0] is page
    assert captured["headless"] is True
    assert context.closed is True
    assert browser.closed is True


def test_fetch_reporting_snapshots_logs_in_without_cookie_file(monkeypatch, tmp_path):
    target = service.SmartFuelPassReportTarget(
        key="dashboard",
        url="https://portal.smartfuelpass.com/dashboard",
    )
    cookie_path = tmp_path / "cookies.json"
    login_calls = []
    _, page, _, _ = install_fake_reporting_playwright(
        monkeypatch,
        {
            target.url: """
                <html>
                    <head><title>Dashboard - Smart Fuel Pass</title></head>
                    <body><h1>Vehicles</h1></body>
                </html>
                """,
        },
    )

    monkeypatch.setattr(
        service,
        "perform_playwright_login",
        lambda page, **kwargs: login_calls.append((page, kwargs)) or "https://portal.smartfuelpass.com/",
    )
    monkeypatch.setattr(service, "_smartfuel_request_timeout_seconds", lambda: 11)
    monkeypatch.setattr(service, "_smartfuel_login_timeout_seconds", lambda: 222)

    snapshots = service.fetch_reporting_snapshots(targets=(target,), cookie_path=cookie_path)

    assert len(snapshots) == 1
    assert len(login_calls) == 1
    assert login_calls[0][0] is page
    assert login_calls[0][1]["timeout_seconds"] == 222
    assert page.default_timeout == 11000
    assert not cookie_path.exists()


def test_fetch_reporting_snapshots_rejects_login_page_after_password_login(monkeypatch):
    target = service.SmartFuelPassReportTarget(
        key="dashboard",
        url="https://portal.smartfuelpass.com/dashboard",
    )
    install_fake_reporting_playwright(
        monkeypatch,
        {
            target.url: """
                <html>
                    <head><title>Login - Smart Fuel Pass</title></head>
                    <body><form id="loginForm"></form></body>
                </html>
                """,
        },
    )

    monkeypatch.setattr(
        service,
        "perform_playwright_login",
        lambda page, **kwargs: "https://portal.smartfuelpass.com/",
    )

    with pytest.raises(service.SmartFuelPassAuthenticationError, match="authenticated reporting page"):
        service.fetch_reporting_snapshots(targets=(target,))


def test_fetch_reporting_snapshots_rejects_disabled_password_login():
    target = service.SmartFuelPassReportTarget(
        key="dashboard",
        url="https://portal.smartfuelpass.com/dashboard",
    )

    with pytest.raises(service.SmartFuelPassAuthenticationError, match="password login"):
        service.fetch_reporting_snapshots(targets=(target,), auto_login=False)


def test_save_reporting_export_writes_json(monkeypatch, tmp_path):
    target = service.SmartFuelPassReportTarget(
        key="dashboard",
        url="https://portal.smartfuelpass.com/",
    )
    snapshot = service.SmartFuelPassPageSnapshot(
        key="dashboard",
        url=target.url,
        title="Dashboard",
        text="Monthly overview",
        html="<html></html>",
    )

    monkeypatch.setattr(service, "fetch_reporting_snapshots", lambda **kwargs: (snapshot,))

    output_path = service.save_reporting_export(output_path=tmp_path / "smartfuelpass.json", targets=(target,))
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["source"] == "smartfuelpass"
    assert payload["page_count"] == 1
    assert payload["pages"][0]["title"] == "Dashboard"


def test_bootstrap_browser_session_fills_credentials_without_persisting_cookies(tmp_path):
    fake_driver = FakeDriver()
    wait_calls = []
    cookie_path = tmp_path / "cookies.json"

    login_url = service.bootstrap_browser_session(
        cookie_path=cookie_path,
        login_url="https://portal.smartfuelpass.com/User/Login",
        email="user@example.com",
        password="secret",
        driver_factory=lambda: fake_driver,
        wait_for_login_completion=lambda driver, login_url, timeout: wait_calls.append(
            (driver, login_url, timeout)
        ),
    )

    assert login_url == "https://portal.smartfuelpass.com/User/Login"
    assert fake_driver.visited_urls == ["https://portal.smartfuelpass.com/User/Login"]
    assert fake_driver.inputs["Email"].values == ["user@example.com"]
    assert fake_driver.inputs["Password"].values == ["secret"]
    assert wait_calls[0][1] == "https://portal.smartfuelpass.com/User/Login"
    assert not cookie_path.exists()
    assert fake_driver.quit_called is True


def test_bootstrap_browser_session_defaults_to_playwright_password_login(monkeypatch, tmp_path):
    captured = {}

    def fake_login(**kwargs):
        captured.update(kwargs)
        return "https://portal.smartfuelpass.com/dashboard"

    monkeypatch.setattr(service, "login_with_playwright", fake_login)

    cookie_path = tmp_path / "cookies.json"
    result = service.bootstrap_browser_session(cookie_path=cookie_path)

    assert result == "https://portal.smartfuelpass.com/dashboard"
    assert captured["headless"] is True
    assert "cookie_path" not in captured
    assert not cookie_path.exists()


def test_auto_login_if_needed_uses_password_login_without_persisting_cookies(monkeypatch, tmp_path):
    page = FakePage()

    class FakeContext:
        def cookies(self):
            return [{"name": "sessionid", "value": "abc123", "domain": "portal.smartfuelpass.com", "path": "/"}]

    captured = {}

    monkeypatch.setattr(
        service,
        "perform_playwright_login",
        lambda page, **kwargs: captured.update({"page": page, **kwargs}),
    )

    cookie_path = tmp_path / "cookies.json"
    did_login = service._auto_login_if_needed(page, FakeContext(), cookie_path=cookie_path, timeout_seconds=30)

    assert did_login is True
    assert captured["page"] is page
    assert captured["timeout_seconds"] == 30
    assert not cookie_path.exists()


def test_auto_login_if_needed_skips_when_page_is_authenticated(tmp_path):
    page = FakePage(
        url="https://portal.smartfuelpass.com/",
        html="<html><head><title>Dashboard</title></head><body>ok</body></html>",
    )

    class FakeContext:
        def cookies(self):
            return []

    did_login = service._auto_login_if_needed(page, FakeContext(), cookie_path=tmp_path / "cookies.json")

    assert did_login is False


def test_fetch_charge_sessions_dataframe_uses_login_timeout_for_auto_login(monkeypatch, tmp_path):
    captured = {}
    expected = pd.DataFrame([{"col": "value"}])

    class FakePageForFetch:
        def __init__(self):
            self.default_timeout = None
            self.visited_urls = []

        def set_default_timeout(self, timeout):
            self.default_timeout = timeout

        def goto(self, url, wait_until=None):
            self.visited_urls.append((url, wait_until))

        def wait_for_load_state(self, state, timeout=None):
            captured["wait_for_load_state"] = (state, timeout)

    class FakeContext:
        def __init__(self):
            self.page = FakePageForFetch()
            self.closed = False

        def new_page(self):
            return self.page

        def close(self):
            self.closed = True

    class FakeBrowser:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class FakePlaywrightManager:
        def __init__(self):
            self.browser = FakeBrowser()
            self.chromium = self

        def launch(self, headless=True):
            captured["headless"] = headless
            return self.browser

    class FakeSyncPlaywright:
        def __enter__(self):
            self.playwright = FakePlaywrightManager()
            return self.playwright

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_context = FakeContext()

    monkeypatch.setattr(service, "_load_playwright_api", lambda: (lambda: FakeSyncPlaywright(), RuntimeError))
    monkeypatch.setattr(service, "_smartfuel_base_url", lambda: "https://portal.smartfuelpass.com/")
    monkeypatch.setattr(service, "_smartfuel_dashboard_path", lambda: "/Fuel/Merchant/Dashboard?contractId=12147&accountId=0")
    monkeypatch.setattr(service, "_smartfuel_request_timeout_seconds", lambda: 15)
    monkeypatch.setattr(service, "_smartfuel_login_timeout_seconds", lambda: 333)
    monkeypatch.setattr(service, "_create_playwright_context", lambda *args, **kwargs: fake_context)
    monkeypatch.setattr(service, "perform_playwright_login", lambda page, **kwargs: captured.update({"login": kwargs}) or "https://portal.smartfuelpass.com/")
    monkeypatch.setattr(service, "open_company_dashboard", lambda page, dashboard_path=None: captured.update({"dashboard_path": dashboard_path}))
    monkeypatch.setattr(service, "open_charging_sessions", lambda page: captured.update({"opened_sessions": True}))
    monkeypatch.setattr(service, "open_summary", lambda page: pytest.fail("fetch should not click the Summary/All filter"))
    monkeypatch.setattr(service, "set_charge_sessions_page_length", lambda page: captured.update({"page_length_set": True}) or True)
    monkeypatch.setattr(service, "load_main_table", lambda page: expected)

    result = service.fetch_charge_sessions_dataframe(cookie_path=tmp_path / "cookies.json")

    assert result is expected
    assert captured["login"]["timeout_seconds"] == 333
    assert captured["opened_sessions"] is True
    assert captured["page_length_set"] is True
    assert fake_context.page.default_timeout == 15000
    assert fake_context.page.visited_urls == []
    assert fake_context.closed is True


def test_last_completed_week_period_uses_previous_calendar_week():
    start, end = service.last_completed_week_period(datetime.datetime(2026, 4, 14, 8, 30))

    assert start == datetime.datetime(2026, 4, 6, 0, 0)
    assert end == datetime.datetime(2026, 4, 12, 23, 59, 59, 999999)


def test_last_completed_week_period_is_stable_during_current_week():
    start, end = service.last_completed_week_period(datetime.datetime(2026, 4, 17, 18, 15))

    assert start == datetime.datetime(2026, 4, 6, 0, 0)
    assert end == datetime.datetime(2026, 4, 12, 23, 59, 59, 999999)


def test_current_month_period_uses_month_start_and_reference_time():
    start, end = service.current_month_period(datetime.datetime(2026, 4, 14, 8, 30))

    assert start == datetime.datetime(2026, 4, 1, 0, 0)
    assert end == datetime.datetime(2026, 4, 14, 8, 30)


def test_parse_datetime_text_accepts_us_portal_format():
    parsed = service._parse_datetime_text("4/11/2026 2:29 PM")

    assert parsed == datetime.datetime(2026, 4, 11, 14, 29)


def test_extract_tariff_label_uses_tariff_text_after_provider_parentheses():
    value = (
        "9b02bfde-74ce-4273 Reimbursement Completed 0 kW 33.489 kWh 79 % null "
        "AdHoc charging - OPT (pax16**128150) ARMEX HOLDING 15Kè + 20,00 % "
        "(ARMEX HOLDING 15Kè) 0.00 Kè (502.34 Kè)"
    )

    assert service._extract_tariff_label(value) == "ARMEX HOLDING 15Kč + 20,00%"


def test_extract_tariff_label_falls_back_to_inline_tariff_without_adhoc_badge():
    value = (
        "cb959684-8892-439e Domácí nabíjení Dokončeno 0 kW 15,955 kWh 86 % "
        "null null ARMEX HOLDING 15Kč 229,35 Kč (239,32 Kč)"
    )

    assert service._extract_tariff_label(value) == "ARMEX HOLDING 15Kč"


def test_build_charge_sessions_report_summarizes_last_week_previous_month_and_total():
    dataframe = pd.DataFrame(
        [
            {
                "Hodnoty měřidel": "13.04.2026 09:15",
                "Čas spuštění": "11.04.2026 13:56 Vzdálené zahájení přes backend systém",
                "Čas ukončení": "11.04.2026 14:29 Ukončeno nabíječkou",
                "Název EV lokace": "Děčín",
                "Konektor EVSE ID": "A1",
                "Veřejné ID": "Domácí nabíjení Dokončeno 0 kW 33,489 kWh 79 % null AdHoc nabíjení - OPT (pax16**128150) ARMEX HOLDING 15Kč + 20,00 % (ARMEX HOLDING 15Kč) 0,00 Kč (120,50 Kč)",
                "Suma": "120,50 Kč",
            },
            {
                "Hodnoty měřidel": "10.04.2026 12:45",
                "Čas spuštění": "10.04.2026 12:00 Vzdálené zahájení přes backend systém",
                "Čas ukončení": "10.04.2026 12:45 Ukončeno nabíječkou",
                "Název EV lokace": "Děčín",
                "Konektor EVSE ID": "A2",
                "Veřejné ID": "Domácí nabíjení Dokončeno 0 kW 20,000 kWh 71 % null AdHoc nabíjení - OPT (pax16**128150) ARMEX HOLDING 15Kč + 20,00 % (ARMEX HOLDING 15Kč) 0,00 Kč (200,00 Kč)",
                "Suma": "200,00 Kč",
            },
            {
                "Hodnoty měřidel": "02.04.2026 11:20",
                "Čas spuštění": "02.04.2026 10:50 Vzdálené zahájení přes backend systém",
                "Čas ukončení": "02.04.2026 11:20 Ukončeno nabíječkou",
                "Název EV lokace": "Ústí nad Labem",
                "Konektor EVSE ID": "A3",
                "Veřejné ID": "Domácí nabíjení Dokončeno 0 kW 15,000 kWh 74 % null AdHoc nabíjení - OPT (pax16**128150) ARMEX HOLDING 15Kč + 20,00 % (ARMEX HOLDING 15Kč) 0,00 Kč (150,00 Kč)",
                "Suma": "150,00 Kč",
            },
            {
                "Hodnoty měřidel": "20.03.2026 08:30",
                "Čas spuštění": "20.03.2026 07:45 Vzdálené zahájení přes backend systém",
                "Čas ukončení": "20.03.2026 08:30 Ukončeno nabíječkou",
                "Název EV lokace": "Praha",
                "Konektor EVSE ID": "B1",
                "Veřejné ID": "Domácí nabíjení Dokončeno 0 kW 12,500 kWh 71 % null AdHoc nabíjení - Web (Google pay) ARMEX HOLDING 15Kč + 20,00 % (ARMEX HOLDING 15Kč) 0,00 Kč (300,00 Kč)",
                "Suma": "300,00 Kč",
            },
            {
                "Hodnoty měřidel": "05.03.2026 14:10",
                "Čas spuštění": "05.03.2026 13:40 Vzdálené zahájení přes backend systém",
                "Čas ukončení": "05.03.2026 14:10 Ukončeno nabíječkou",
                "Název EV lokace": "Brno",
                "Konektor EVSE ID": "C1",
                "Veřejné ID": "Domácí nabíjení Dokončeno 0 kW 8,250 kWh 71 % null AdHoc nabíjení - OPT (pax16**128150) ARMEX HOLDING 15Kč + 20,00 % (ARMEX HOLDING 15Kč) 0,00 Kč (99,90 Kč)",
                "Suma": "99,90 Kč",
            },
            {
                "Hodnoty měřidel": "11.02.2026 18:00",
                "Čas spuštění": "11.02.2026 17:10 Vzdálené zahájení přes backend systém",
                "Čas ukončení": "11.02.2026 18:00 Ukončeno nabíječkou",
                "Název EV lokace": "Ostrava",
                "Konektor EVSE ID": "D1",
                "Veřejné ID": "Domácí nabíjení Dokončeno 0 kW 5,000 kWh 71 % null AdHoc nabíjení - OPT (pax16**128150) ARMEX HOLDING 15Kč + 20,00 % (ARMEX HOLDING 15Kč) 0,00 Kč (50,00 Kč)",
                "Suma": "50,00 Kč",
            },
            {
                "Hodnoty měřidel": "not-a-date",
                "Čas spuštění": "-",
                "Čas ukončení": "-",
                "Název EV lokace": "Invalid",
                "Konektor EVSE ID": "X",
                "Veřejné ID": "Domácí nabíjení Zrušeno 0 kW 0 kWh",
                "Suma": "10,00 Kč",
            },
            {
                "Hodnoty měřidel": "-",
                "Čas spuštění": "11.02.2026 17:12 Vzdálené zahájení přes backend systém",
                "Čas ukončení": "- Zrušeno systémem",
                "Název EV lokace": "Armex - Budova E null",
                "Konektor EVSE ID": "X1",
                "Veřejné ID": "Domácí nabíjení Zrušeno 0 kW 0 kWh null AdHoc nabíjení",
                "Suma": "-",
            },
        ]
    )

    report = service.build_charge_sessions_report(
        dataframe,
        reference_datetime=datetime.datetime(2026, 4, 14, 8, 30),
        subject_name="ARMEX HOLDING, a.s.",
    )

    assert report.invalid_row_count == 1
    assert report.last_week.session_count == 2
    assert report.last_week.total_amount == 320.5
    assert report.previous_month.session_count == 2
    assert report.previous_month.total_amount == 399.9
    assert report.total.session_count == 6
    assert report.total.total_amount == 920.4
    assert report.last_week_rows[0].date_range_label == "11.04.2026 13:56 - 14:29"
    assert report.last_week_rows[0].kwh_label == "33,489 kWh"
    assert report.last_week_rows[0].tariff_label == "ARMEX HOLDING 15Kč + 20,00%"
    assert len(report.current_month_rows) == 3
    assert report.current_month_rows[0].date_range_label == "11.04.2026 13:56 - 14:29"
    assert report.current_month_rows[-1].date_range_label == "02.04.2026 10:50 - 11:20"
    assert report.previous_month_rows[0].tariff_label == "ARMEX HOLDING 15Kč + 20,00%"


def test_build_charge_sessions_report_html_contains_summary_sections():
    dataframe = pd.DataFrame(
        [
            {
                "Hodnoty měřidel": "13.04.2026 09:15",
                "Čas spuštění": "11.04.2026 13:56 Vzdálené zahájení přes backend systém",
                "Čas ukončení": "11.04.2026 14:29 Ukončeno nabíječkou",
                "Název EV lokace": "Armex - Budova E null",
                "Konektor EVSE ID": "A1",
                "Veřejné ID": "Domácí nabíjení Dokončeno 0 kW 33,489 kWh 79 % null AdHoc nabíjení - OPT (pax16**128150) ARMEX HOLDING 15Kč + 20,00 % (ARMEX HOLDING 15Kč) 0,00 Kč (120,50 Kč)",
                "Suma": "120,50 Kč",
            },
            {
                "Hodnoty měřidel": "02.04.2026 11:20",
                "Čas spuštění": "02.04.2026 10:50 Vzdálené zahájení přes backend systém",
                "Čas ukončení": "02.04.2026 11:20 Ukončeno nabíječkou",
                "Název EV lokace": "Ústí nad Labem null",
                "Konektor EVSE ID": "A3",
                "Veřejné ID": "Domácí nabíjení Dokončeno 0 kW 15,000 kWh 74 % null AdHoc nabíjení - OPT (pax16**128150) ARMEX HOLDING 15Kč + 20,00 % (ARMEX HOLDING 15Kč) 0,00 Kč (150,00 Kč)",
                "Suma": "150,00 Kč",
            }
        ]
    )
    report = service.build_charge_sessions_report(
        dataframe,
        reference_datetime=datetime.datetime(2026, 4, 14, 8, 30),
        subject_name="ARMEX HOLDING, a.s.",
    )

    html = service.build_charge_sessions_report_html(report)

    assert "data:image/svg+xml;base64," in html
    assert "data:image/png;base64," in html
    assert "Poslední týden" in html
    assert "Tento měsíc" in html
    assert "Minulý měsíc" in html
    assert "Celkem" in html
    assert "Subjekt:" in html
    assert "Vygenerováno:" in html
    assert "11.04.2026 13:56 - 14:29" in html
    assert "02.04.2026 10:50 - 11:20" in html
    assert "33,489 kWh" in html
    assert "Armex - Budova E" in html
    assert "Ústí nad Labem" in html
    assert "ARMEX HOLDING 15Kč + 20,00%" in html
    assert ">Tarif<" in html
    assert ">Cena<" in html
    assert "120,50 Kč" in html
    assert html.count("11.04.2026 13:56 - 14:29") == 2
    assert "<h2>Poslední týden</h2>" in html
    assert "První relace:" not in html
    assert "Poslední relace:" not in html
    assert "Souhrn za poslední týden" not in html
    assert "Smart Fuel Pass logo" in html
    assert "ARMEX logo" in html


def test_build_charge_sessions_report_from_portal_retries_missing_table(monkeypatch):
    dataframe = pd.DataFrame(
        [
            {
                "Hodnoty měřidel": "13.04.2026 09:15",
                "Čas spuštění": "11.04.2026 13:56 Vzdálené zahájení přes backend systém",
                "Čas ukončení": "11.04.2026 14:29 Ukončeno nabíječkou",
                "Název EV lokace": "Armex - Budova E null",
                "Konektor EVSE ID": "A1",
                "Veřejné ID": "Domácí nabíjení Dokončeno 0 kW 33,489 kWh 79 % null AdHoc nabíjení - OPT (pax16**128150) ARMEX HOLDING 15Kč + 20,00 % (ARMEX HOLDING 15Kč) 0,00 Kč (120,50 Kč)",
                "Suma": "120,50 Kč",
            }
        ]
    )
    fetch_calls = []
    sleep_calls = []

    def fake_fetch_charge_sessions_dataframe(**kwargs):
        fetch_calls.append(kwargs)
        if len(fetch_calls) == 1:
            raise service.SmartFuelPassError(service.TABLE_NOT_FOUND_MESSAGE)
        return dataframe

    def fake_config(key, default="", cast=None):
        mapping = {
            "SMARTFUELPASS_FETCH_ATTEMPTS": "2",
            "SMARTFUELPASS_FETCH_RETRY_DELAY_SECONDS": "0",
        }
        value = mapping.get(key, default)
        return cast(value) if cast is not None else value

    monkeypatch.setattr(service, "fetch_charge_sessions_dataframe", fake_fetch_charge_sessions_dataframe)
    monkeypatch.setattr(service, "config", fake_config)
    monkeypatch.setattr(service.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    report = service.build_charge_sessions_report_from_portal(
        reference_datetime=datetime.datetime(2026, 4, 14, 8, 30),
        subject_name="ARMEX HOLDING, a.s.",
    )

    assert len(fetch_calls) == 2
    assert sleep_calls == []
    assert report.total.session_count == 1
    assert report.total.total_amount == 120.5


def test_fetch_charge_sessions_dataframe_with_retries_forwards_timeout_and_dashboard(monkeypatch):
    expected = pd.DataFrame([{"col": "value"}])
    fetch_calls = []

    monkeypatch.setattr(
        service,
        "fetch_charge_sessions_dataframe",
        lambda **kwargs: fetch_calls.append(kwargs) or expected,
    )

    result = service.fetch_charge_sessions_dataframe_with_retries(
        cookie_path="cookies.json",
        headless=False,
        dashboard_path="/Report/List",
        timeout_seconds=21,
        attempts=1,
    )

    assert result is expected
    assert fetch_calls == [
        {
            "cookie_path": "cookies.json",
            "headless": False,
            "dashboard_path": "/Report/List",
            "timeout_seconds": 21,
        }
    ]


def test_load_main_table_error_includes_url_and_selector_counts(monkeypatch):
    class FakeLocatorCollection:
        def count(self):
            return 0

        def nth(self, index):
            raise AssertionError(index)

    class FakePageForTableSearch:
        def __init__(self):
            self.url = "https://portal.smartfuelpass.com/Fuel/Merchant/Dashboard?contractId=12147&accountId=0"

        def locator(self, selector):
            return FakeLocatorCollection()

        def wait_for_timeout(self, timeout):
            return None

    time_values = iter((0.0, 2.0))
    monkeypatch.setattr(service.time, "time", lambda: next(time_values))

    with pytest.raises(service.SmartFuelPassError) as exc_info:
        service.load_main_table(FakePageForTableSearch(), timeout_seconds=1)

    message = str(exc_info.value)
    assert service.TABLE_NOT_FOUND_MESSAGE in message
    assert "URL: https://portal.smartfuelpass.com/Fuel/Merchant/Dashboard?contractId=12147&accountId=0" in message
    assert "main table:visible=0" in message
    assert '[role="main"] table:visible=0' in message
    assert "table:visible=0" in message


def test_build_charge_sessions_report_from_database_uses_synced_rows(monkeypatch):
    class FakeQuery:
        def __init__(self, rows):
            self.rows = rows

        def order_by(self, *args):
            return self

        def all(self):
            return self.rows

    class FakeSession:
        def __init__(self, rows):
            self.rows = rows

        def query(self, model):
            return FakeQuery(self.rows)

    rows = [
        SimpleNamespace(
            id_relace="rel-001",
            kwh=33.489,
            tarif="ARMEX HOLDING 15Kč + 20,00%",
            battery_status=79,
            suma=120.50,
            connector_id="A1",
            started_at=datetime.datetime(2026, 4, 11, 13, 56),
            ended_at=datetime.datetime(2026, 4, 11, 14, 29),
            lokace="Armex - Budova E",
            rychlost_nabijeni=60.889,
        ),
        SimpleNamespace(
            id_relace="rel-002",
            kwh=15.0,
            tarif="ARMEX HOLDING 15Kč",
            battery_status=86,
            suma=210.0,
            connector_id="A2",
            started_at=datetime.datetime(2026, 4, 2, 10, 50),
            ended_at=datetime.datetime(2026, 4, 2, 11, 20),
            lokace="Ústí nad Labem",
            rychlost_nabijeni=30.0,
        ),
    ]
    monkeypatch.setattr(service, "ensure_smartfuelpass_tables", lambda: None)

    report = service.build_charge_sessions_report_from_database(
        db_session=FakeSession(rows),
        reference_datetime=datetime.datetime(2026, 4, 14, 8, 30),
        subject_name="ARMEX HOLDING, a.s.",
    )

    assert report.source_row_count == 2
    assert report.invalid_row_count == 0
    assert report.last_week.session_count == 1
    assert report.last_week.connector_count == 1
    assert report.last_week_rows[0].connector_id == "A1"
    assert report.last_week_rows[0].date_range_label == "11.04.2026 13:56 - 14:29"
    assert report.last_week_rows[0].kwh_label == "33,489 kWh"
    assert report.current_month_rows[-1].location_name == "Ústí nad Labem"


def test_send_charge_sessions_report_email_generates_pdf_and_sends_attachment(monkeypatch, tmp_path):
    dataframe = pd.DataFrame(
        [
            {
                "Hodnoty měřidel": "13.04.2026 09:15",
                "Čas spuštění": "11.04.2026 13:56 Vzdálené zahájení přes backend systém",
                "Čas ukončení": "11.04.2026 14:29 Ukončeno nabíječkou",
                "Název EV lokace": "Armex - Budova E null",
                "Konektor EVSE ID": "A1",
                "Veřejné ID": "Domácí nabíjení Dokončeno 0 kW 33,489 kWh 79 % null AdHoc nabíjení - OPT (pax16**128150) ARMEX HOLDING 15Kč + 20,00 % (ARMEX HOLDING 15Kč) 0,00 Kč (120,50 Kč)",
                "Suma": "120,50 Kč",
            },
            {
                "Hodnoty měřidel": "20.03.2026 08:30",
                "Čas spuštění": "20.03.2026 07:45 Vzdálené zahájení přes backend systém",
                "Čas ukončení": "20.03.2026 08:30 Ukončeno nabíječkou",
                "Název EV lokace": "Praha",
                "Konektor EVSE ID": "B1",
                "Veřejné ID": "Domácí nabíjení Dokončeno 0 kW 12,500 kWh 71 % null AdHoc nabíjení - Web (Google pay) ARMEX HOLDING 15Kč + 20,00 % (ARMEX HOLDING 15Kč) 0,00 Kč (300,00 Kč)",
                "Suma": "300,00 Kč",
            },
        ]
    )
    report = service.build_charge_sessions_report(
        dataframe,
        reference_datetime=datetime.datetime(2026, 4, 14, 8, 30),
        subject_name="ARMEX HOLDING, a.s.",
    )
    pdf_bytes = b"%PDF-1.4\n%fake"
    sent_messages = []

    monkeypatch.setattr(
        service,
        "build_charge_sessions_report_from_database",
        lambda **kwargs: report,
    )
    monkeypatch.setattr(
        service,
        "build_charge_sessions_report_from_portal",
        lambda **kwargs: pytest.fail("weekly email report must use synced database rows"),
    )
    monkeypatch.setattr(
        service,
        "render_charge_sessions_report_pdf",
        lambda generated_report: pdf_bytes,
    )
    monkeypatch.setattr(
        service,
        "send_email_outlook",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    def fake_config(key, default=""):
        mapping = {
            "SMARTFUELPASS_WEEKLY_REPORT_RECIPIENTS": "first@example.com, second@example.com",
            "SMARTFUELPASS_WEEKLY_REPORT_SENDER_ALIAS": "upozorneni@example.com",
            "O_EMAIL_UPOZORNENI": "upozorneni@example.com",
        }
        return mapping.get(key, default)

    monkeypatch.setattr(service, "config", fake_config)

    result = service.send_charge_sessions_report_email(reference_datetime=datetime.datetime(2026, 4, 14, 8, 30))

    assert result["recipient_count"] == 2
    assert result["pdf_filename"] == "smartfuelpass_charge_sessions_20260414_083000.pdf"
    assert result["pdf_size_bytes"] == len(pdf_bytes)
    assert len(sent_messages) == 2
    assert sent_messages[0]["email_receiver"] == "first@example.com"
    assert sent_messages[1]["email_receiver"] == "second@example.com"
    assert sent_messages[0]["sender_alias"] == "upozorneni@example.com"
    assert sent_messages[0]["is_html"] is True
    assert sent_messages[0]["attachments"] == [
        ("smartfuelpass_charge_sessions_20260414_083000.pdf", pdf_bytes, "application", "pdf")
    ]
    assert "Smart Fuel Pass | report nabijecich relaci | 14.04.2026" == sent_messages[0]["subject"]
    assert "V příloze je přiložen aktuální PDF report" in sent_messages[0]["body"]
    assert "smartfuelpass_charge_sessions_20260414_083000.pdf" in sent_messages[0]["body"]
    assert "Poslední týden" in sent_messages[0]["body"]
