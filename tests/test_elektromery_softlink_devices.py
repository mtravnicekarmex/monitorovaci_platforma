import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.elektromery.database.models import Elektromer_areal_Zarizeni
from moduly.mereni.elektromery import softlink_devices


class _FakeColumnQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return [(row,) for row in self.rows]


class _FakeExistingIdsSession:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False

    def query(self, *args, **kwargs):
        return _FakeColumnQuery(self.rows)

    def close(self):
        self.closed = True


class _FakeSaveQuery:
    def __init__(self, session):
        self.session = session

    def filter(self, *args, **kwargs):
        return self

    def one_or_none(self):
        return self.session.queued_results.pop(0)


class _FakeSaveSession:
    def __init__(self, queued_results):
        self.queued_results = list(queued_results)
        self.added = []
        self.commit_calls = 0
        self.rollback_calls = 0
        self.closed = False

    def query(self, *args, **kwargs):
        return _FakeSaveQuery(self)

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def close(self):
        self.closed = True


def test_normalize_softlink_device_response_extracts_unique_candidates():
    status, devices = softlink_devices.normalize_softlink_device_response(
        {
            "status": 200,
            "data": [
                {
                    "me_id": 101,
                    "me_desc": "Rozvaděč A",
                    "me_serial": 555,
                    "me_typ_pzn": "EMH",
                    "me_plom": "P-1",
                    "me_zapoc": "123.4",
                    "mis_id": 10,
                    "met_id": 20,
                    "me_od": "2026-04-01",
                    "me_do": "2026-12-31",
                    "me_over": "2028-01-15",
                },
                {
                    "me_id": 101,
                    "me_desc": "Duplicate",
                },
                {
                    "me_desc": "Bez ID",
                },
            ],
        }
    )

    assert status == 200
    assert len(devices) == 1
    assert devices[0].softlink_id == 101
    assert devices[0].description == "Rozvaděč A"
    assert devices[0].serial_number == 555
    assert devices[0].meter_type == "EMH"
    assert devices[0].mis_id == 10
    assert devices[0].met_id == 20
    assert devices[0].valid_from == datetime.datetime(2026, 4, 1, 0, 0)


def test_discover_new_softlink_devices_filters_existing_softlink_ids():
    def fake_fetcher():
        return {
            "status": 200,
            "data": [
                {"me_id": 101, "me_desc": "A"},
                {"me_id": 202, "me_desc": "B"},
            ],
        }

    fake_session = _FakeExistingIdsSession([101])
    report = softlink_devices.discover_new_softlink_devices(
        fetch_fn=fake_fetcher,
        session_factory=lambda: fake_session,
        generated_at=datetime.datetime(2026, 4, 30, 8, 0, 0),
    )

    assert report.total_softlink_devices == 2
    assert report.matched_device_count == 1
    assert report.new_device_count == 1
    assert report.new_devices[0].softlink_id == 202
    assert fake_session.closed is True


def test_normalize_softlink_device_response_tolerates_invalid_optional_numeric_fields():
    status, devices = softlink_devices.normalize_softlink_device_response(
        {
            "status": 200,
            "data": [
                {
                    "me_id": 404,
                    "me_desc": "Rozvaděč D",
                    "me_serial": "ABC-404",
                    "mis_id": "MIS-X",
                    "met_id": True,
                },
            ],
        }
    )

    assert status == 200
    assert len(devices) == 1
    assert devices[0].softlink_id == 404
    assert devices[0].serial_number is None
    assert devices[0].mis_id is None
    assert devices[0].met_id is None


def test_send_weekly_new_elektromery_report_sends_html_email(monkeypatch):
    sent_messages = []
    report = softlink_devices.SoftlinkDeviceDiscoveryReport(
        generated_at=datetime.datetime(2026, 4, 30, 8, 0, 0),
        source_status=200,
        total_softlink_devices=5,
        matched_device_count=4,
        new_devices=(
            softlink_devices.SoftlinkDeviceCandidate(
                softlink_id=202,
                description="Rozvaděč B",
                serial_number=777,
                meter_type="EMH",
                plomb="P-2",
                initial_value=10.0,
                mis_id=11,
                met_id=22,
                valid_from=datetime.datetime(2026, 4, 1, 0, 0),
                valid_to=None,
                calibration_valid_until=None,
                raw_payload={},
            ),
        ),
    )

    monkeypatch.setattr(softlink_devices, "discover_new_softlink_devices", lambda **kwargs: report)
    monkeypatch.setattr(softlink_devices, "_load_recipients", lambda: ("elektro@armex.cz",))
    monkeypatch.setattr(softlink_devices, "_resolve_sender_alias", lambda: "Monitoring")
    monkeypatch.setattr(softlink_devices, "send_email_outlook", lambda **kwargs: sent_messages.append(kwargs))

    result = softlink_devices.send_weekly_new_elektromery_report()

    assert result == {
        "title": "Elektromery | tydenni kontrola novych elektromeru | 30.04.2026",
        "recipient_count": 1,
        "recipients": ("elektro@armex.cz",),
        "total_softlink_devices": 5,
        "matched_device_count": 4,
        "new_device_count": 1,
    }
    assert len(sent_messages) == 1
    assert sent_messages[0]["email_receiver"] == "elektro@armex.cz"
    assert sent_messages[0]["sender_alias"] == "Monitoring"
    assert sent_messages[0]["is_html"] is True
    assert "Rozvaděč B" in sent_messages[0]["body"]


def test_save_new_softlink_device_inserts_new_ms_row():
    candidate = softlink_devices.SoftlinkDeviceCandidate(
        softlink_id=202,
        description="Rozvaděč B",
        serial_number=777,
        meter_type="EMH",
        plomb="P-2",
        initial_value=10.0,
        mis_id=11,
        met_id=22,
        valid_from=datetime.datetime(2026, 4, 1, 0, 0),
        valid_to=datetime.datetime(2026, 12, 31, 0, 0),
        calibration_valid_until=datetime.datetime(2028, 1, 15, 0, 0),
        raw_payload={},
    )
    fake_session = _FakeSaveSession([None, None])

    result = softlink_devices.save_new_softlink_device(
        candidate,
        {
            "identifikace": "OM-202",
            "seriove_cislo": "777",
            "ean": "8591824000001",
            "pozice": "TS1",
            "podruzny": "ANO",
            "mistnost": "Rozvodna",
            "umisteni": "Rozvaděč B",
            "napaji": "Technologie",
            "koncovy_odberatel": "ARMEX",
            "platnost_cejchu": "15.01.2028",
            "jistic": "80A",
            "typ_merice": "EMH",
            "rozvadec": "R1",
            "typ_tarifu": "C25d",
            "platnost_od": "01.04.2026",
            "platnost_do": "31.12.2026",
            "plomb": "P-2",
            "mis_id": "11",
            "met_id": "22",
            "foto": "foto.jpg",
        },
        session_factory=lambda: fake_session,
    )

    assert result.action == "inserted"
    assert result.identifikace == "OM-202"
    assert result.softlink_id == 202
    assert fake_session.commit_calls == 1
    assert fake_session.rollback_calls == 0
    assert len(fake_session.added) == 1
    added_row = fake_session.added[0]
    assert isinstance(added_row, Elektromer_areal_Zarizeni)
    assert added_row.softlink_id == 202
    assert added_row.identifikace == "OM-202"
    assert added_row.umisteni == "Rozvaděč B"
    assert added_row.typ_merice == "EMH"


def test_save_new_softlink_device_updates_existing_ident_without_softlink_id():
    candidate = softlink_devices.SoftlinkDeviceCandidate(
        softlink_id=303,
        description="Rozvaděč C",
        serial_number=888,
        meter_type="Landis",
        plomb=None,
        initial_value=None,
        mis_id=None,
        met_id=None,
        valid_from=None,
        valid_to=None,
        calibration_valid_until=None,
        raw_payload={},
    )
    existing_row = Elektromer_areal_Zarizeni(identifikace="OM-303")
    existing_row.softlink_id = None
    fake_session = _FakeSaveSession([None, existing_row])

    result = softlink_devices.save_new_softlink_device(
        candidate,
        {
            "identifikace": "OM-303",
            "seriove_cislo": "888",
            "ean": "",
            "pozice": "",
            "podruzny": "",
            "mistnost": "",
            "umisteni": "Rozvaděč C",
            "napaji": "",
            "koncovy_odberatel": "",
            "platnost_cejchu": "",
            "jistic": "",
            "typ_merice": "Landis",
            "rozvadec": "",
            "typ_tarifu": "",
            "platnost_od": "",
            "platnost_do": "",
            "plomb": "",
            "mis_id": "",
            "met_id": "",
            "foto": "",
        },
        session_factory=lambda: fake_session,
    )

    assert result.action == "updated"
    assert existing_row.softlink_id == 303
    assert existing_row.identifikace == "OM-303"
    assert fake_session.commit_calls == 1
    assert fake_session.added == []
