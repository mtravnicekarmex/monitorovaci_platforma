import datetime
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.smartfuelpass import service


class FakeResponse:
    def __init__(self, *, url: str, text: str, status_code: int = 200):
        self.url = url
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.closed = False

    def get(self, url, timeout=None, allow_redirects=True):
        del timeout, allow_redirects
        return self.responses[url]

    def close(self):
        self.closed = True


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


def test_create_authenticated_session_loads_cookie_payload(tmp_path):
    cookie_path = tmp_path / "cookies.json"
    cookie_path.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "sessionid",
                        "value": "abc123",
                        "domain": "portal.smartfuelpass.com",
                        "path": "/",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    session = service.create_authenticated_session(cookie_path=cookie_path)

    cookie = next(item for item in session.cookies if item.name == "sessionid")
    assert cookie.value == "abc123"
    assert "User-Agent" in session.headers
    session.close()


def test_fetch_reporting_snapshots_extracts_title_and_text(monkeypatch):
    target = service.SmartFuelPassReportTarget(
        key="dashboard",
        url="https://portal.smartfuelpass.com/dashboard",
    )
    fake_session = FakeSession(
        {
            target.url: FakeResponse(
                url=target.url,
                text="""
                <html>
                    <head><title>Dashboard - Smart Fuel Pass</title></head>
                    <body>
                        <script>hidden()</script>
                        <h1>Vehicles</h1>
                        <p>Monthly overview</p>
                    </body>
                </html>
                """,
            )
        }
    )

    monkeypatch.setattr(service, "create_authenticated_session", lambda **kwargs: fake_session)

    snapshots = service.fetch_reporting_snapshots(targets=(target,))

    assert len(snapshots) == 1
    assert snapshots[0].title == "Dashboard - Smart Fuel Pass"
    assert "Vehicles" in snapshots[0].text
    assert "hidden()" not in snapshots[0].text
    assert fake_session.closed is True


def test_fetch_reporting_snapshots_auto_logs_in_when_cookie_session_is_missing(monkeypatch, tmp_path):
    target = service.SmartFuelPassReportTarget(
        key="dashboard",
        url="https://portal.smartfuelpass.com/dashboard",
    )
    fake_session = FakeSession(
        {
            target.url: FakeResponse(
                url=target.url,
                text="""
                <html>
                    <head><title>Dashboard - Smart Fuel Pass</title></head>
                    <body><h1>Vehicles</h1></body>
                </html>
                """,
            )
        }
    )
    cookie_path = tmp_path / "cookies.json"
    create_calls = {"count": 0}
    login_calls = []

    def fake_create_authenticated_session(**kwargs):
        create_calls["count"] += 1
        assert kwargs["cookie_path"] == cookie_path
        if create_calls["count"] == 1:
            raise service.SmartFuelPassAuthenticationError("missing cookies")
        return fake_session

    def fake_auto_login(**kwargs):
        login_calls.append(kwargs)
        return cookie_path

    monkeypatch.setattr(service, "create_authenticated_session", fake_create_authenticated_session)
    monkeypatch.setattr(service, "login_and_save_session_with_playwright", fake_auto_login)

    snapshots = service.fetch_reporting_snapshots(targets=(target,), cookie_path=cookie_path)

    assert len(snapshots) == 1
    assert create_calls["count"] == 2
    assert len(login_calls) == 1
    assert login_calls[0]["cookie_path"] == cookie_path
    assert login_calls[0]["headless"] is True
    assert fake_session.closed is True


def test_fetch_reporting_snapshots_retries_after_expired_session(monkeypatch, tmp_path):
    target = service.SmartFuelPassReportTarget(
        key="dashboard",
        url="https://portal.smartfuelpass.com/dashboard",
    )
    expired_session = FakeSession(
        {
            target.url: FakeResponse(
                url="https://portal.smartfuelpass.com/User/Login?ReturnUrl=%2Fdashboard",
                text="""
                <html>
                    <head><title>Login - Smart Fuel Pass</title></head>
                    <body><form id="loginForm"></form></body>
                </html>
                """,
            )
        }
    )
    refreshed_session = FakeSession(
        {
            target.url: FakeResponse(
                url=target.url,
                text="""
                <html>
                    <head><title>Dashboard - Smart Fuel Pass</title></head>
                    <body><p>Monthly overview</p></body>
                </html>
                """,
            )
        }
    )
    sessions = [expired_session, refreshed_session]
    cookie_path = tmp_path / "cookies.json"
    login_calls = []

    monkeypatch.setattr(
        service,
        "create_authenticated_session",
        lambda **kwargs: sessions.pop(0),
    )
    monkeypatch.setattr(
        service,
        "login_and_save_session_with_playwright",
        lambda **kwargs: login_calls.append(kwargs) or cookie_path,
    )

    snapshots = service.fetch_reporting_snapshots(targets=(target,), cookie_path=cookie_path)

    assert len(snapshots) == 1
    assert snapshots[0].title == "Dashboard - Smart Fuel Pass"
    assert len(login_calls) == 1
    assert login_calls[0]["cookie_path"] == cookie_path
    assert expired_session.closed is True
    assert refreshed_session.closed is True


def test_fetch_reporting_snapshots_rejects_login_page(monkeypatch):
    target = service.SmartFuelPassReportTarget(
        key="dashboard",
        url="https://portal.smartfuelpass.com/dashboard",
    )
    fake_session = FakeSession(
        {
            target.url: FakeResponse(
                url="https://portal.smartfuelpass.com/User/Login?ReturnUrl=%2Fdashboard",
                text="""
                <html>
                    <head><title>Login - Smart Fuel Pass</title></head>
                    <body><form id="loginForm"></form></body>
                </html>
                """,
            )
        }
    )

    monkeypatch.setattr(service, "create_authenticated_session", lambda **kwargs: fake_session)

    with pytest.raises(service.SmartFuelPassError, match="expired or unauthenticated"):
        service.fetch_reporting_snapshots(targets=(target,), auto_login=False)

    assert fake_session.closed is True


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


def test_bootstrap_browser_session_fills_credentials_and_persists_cookies(tmp_path):
    fake_driver = FakeDriver()
    wait_calls = []

    cookie_path = service.bootstrap_browser_session(
        cookie_path=tmp_path / "cookies.json",
        login_url="https://portal.smartfuelpass.com/User/Login",
        email="user@example.com",
        password="secret",
        driver_factory=lambda: fake_driver,
        wait_for_login_completion=lambda driver, login_url, timeout: wait_calls.append(
            (driver, login_url, timeout)
        ),
    )

    payload = json.loads(cookie_path.read_text(encoding="utf-8"))

    assert fake_driver.visited_urls == ["https://portal.smartfuelpass.com/User/Login"]
    assert fake_driver.inputs["Email"].values == ["user@example.com"]
    assert fake_driver.inputs["Password"].values == ["secret"]
    assert wait_calls[0][1] == "https://portal.smartfuelpass.com/User/Login"
    assert payload[0]["name"] == "sessionid"
    assert fake_driver.quit_called is True


def test_bootstrap_browser_session_defaults_to_playwright_auto_login(monkeypatch, tmp_path):
    captured = {}

    def fake_auto_login(**kwargs):
        captured.update(kwargs)
        path = tmp_path / "cookies.json"
        path.write_text("[]", encoding="utf-8")
        return path

    monkeypatch.setattr(service, "login_and_save_session_with_playwright", fake_auto_login)

    result = service.bootstrap_browser_session(cookie_path=tmp_path / "cookies.json")

    assert result == tmp_path / "cookies.json"
    assert captured["cookie_path"] == tmp_path / "cookies.json"
    assert captured["headless"] is True


def test_auto_login_if_needed_persists_new_cookies(monkeypatch, tmp_path):
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

    payload = json.loads(cookie_path.read_text(encoding="utf-8"))

    assert did_login is True
    assert captured["page"] is page
    assert payload[0]["name"] == "sessionid"


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


def test_last_completed_week_period_uses_previous_seven_full_days():
    start, end = service.last_completed_week_period(datetime.datetime(2026, 4, 14, 8, 30))

    assert start == datetime.datetime(2026, 4, 7, 0, 0)
    assert end == datetime.datetime(2026, 4, 13, 23, 59, 59, 999999)


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
    assert len(report.current_month_rows) == 1
    assert report.current_month_rows[0].date_range_label == "02.04.2026 10:50 - 11:20"
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
    assert html.count("11.04.2026 13:56 - 14:29") == 1
    assert "První relace:" not in html
    assert "Poslední relace:" not in html
    assert "Souhrn za poslední týden" not in html
    assert "Smart Fuel Pass logo" in html
