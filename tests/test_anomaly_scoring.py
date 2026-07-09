import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.plynomery import plynomery_anomaly
from moduly.mereni.vodomery import vodomery_anomaly


class FakeScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, *, state, measurements, profile_rows=None, snapshot_rows=None):
        self.state = state
        self.measurements = measurements
        self.profile_rows = profile_rows or []
        self.snapshot_rows = snapshot_rows or []
        self.insert_statement = None
        self.insert_rows = None
        self.update_statement = None
        self.commit_calls = 0
        self.snapshot_select_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, model, key):
        return self.state

    def add(self, obj):
        self.state = obj

    def commit(self):
        self.commit_calls += 1

    def query(self, model):
        return FakeQuery(self.measurements)

    def execute(self, statement, params=None):
        if params is not None:
            self.insert_statement = statement
            self.insert_rows = params
            return SimpleNamespace(rowcount=len(params))

        column_descriptions = getattr(statement, "column_descriptions", None) or []
        if column_descriptions:
            entity = column_descriptions[0].get("entity")
            if entity in (
                vodomery_anomaly.VodomeryProfilesAnomaly,
                plynomery_anomaly.PlynomeryProfilesAnomaly,
            ):
                return FakeScalarResult(self.profile_rows)
            if entity is vodomery_anomaly.PredictionSelectedModelSnapshot:
                self.snapshot_select_count += 1
                return FakeScalarResult(self.snapshot_rows)

        self.update_statement = statement
        return FakeScalarResult([])


def _normalize_sql(statement) -> str:
    compiled = statement.compile(dialect=postgresql.dialect())
    return " ".join(str(compiled).upper().split())


def test_vodomery_scoring_uses_conflict_safe_insert(monkeypatch):
    profile = SimpleNamespace(
        identifikace="A_V1",
        interval_minutes=15,
        day_of_week=1,
        slot=12,
        mean=1.0,
        std=0.5,
        median=1.0,
        p10=0.2,
        p90=1.5,
    )
    measurement = SimpleNamespace(
        id=123,
        identifikace="A_V1",
        interval_minutes=15,
        day_of_week=1,
        slot=12,
        delta=1.8,
        date=datetime.datetime(2026, 4, 21, 13, 30),
    )
    session = FakeSession(
        state=SimpleNamespace(model_version=1, last_measurement_id=100),
        measurements=[measurement],
        profile_rows=[profile],
    )

    monkeypatch.setattr(vodomery_anomaly, "Session", lambda *args, **kwargs: session)
    monkeypatch.setattr(vodomery_anomaly, "config", lambda *args, **kwargs: False)

    inserted = vodomery_anomaly.score_new_measurements(model_version=1, batch_size=10)

    assert inserted == 1
    assert session.commit_calls == 1
    assert session.insert_rows == [
        {
            "measurement_id": 123,
            "identifikace": "A_V1",
            "date": datetime.datetime(2026, 4, 21, 13, 30),
            "actual_value": 1.8,
            "expected_mean": 1.0,
            "expected_std": 0.5,
            "expected_median": 1.0,
            "expected_p10": 0.2,
            "expected_p90": 1.5,
            "deviation": 0.8,
            "z_score": 1.6,
            "is_anomaly": True,
            "severity": None,
            "model_version": 1,
        }
    ]
    assert "ON CONFLICT (MEASUREMENT_ID, MODEL_VERSION) DO NOTHING" in _normalize_sql(
        session.insert_statement
    )


def test_vodomery_scoring_keeps_global_profile_when_selection_disabled(monkeypatch):
    global_profile = SimpleNamespace(
        model_version=3,
        identifikace="L1_V1",
        interval_minutes=15,
        day_of_week=3,
        slot=48,
        mean=10.0,
        std=2.0,
        median=10.0,
        p10=8.0,
        p90=12.0,
    )
    selected_profile = SimpleNamespace(
        model_version=2,
        identifikace="L1_V1",
        interval_minutes=15,
        day_of_week=3,
        slot=48,
        mean=16.0,
        std=1.0,
        median=16.0,
        p10=12.0,
        p90=20.0,
    )
    measurement = SimpleNamespace(
        id=201,
        identifikace="L1_V1",
        interval_minutes=15,
        day_of_week=3,
        slot=48,
        delta=17.0,
        date=datetime.datetime(2026, 7, 9, 12, 0),
    )
    snapshot = SimpleNamespace(
        identifier="L1_V1",
        selected_model_version=2,
        forecast_period_start=datetime.datetime(2026, 7, 6),
        forecast_period_end=datetime.datetime(2026, 7, 13),
    )
    session = FakeSession(
        state=SimpleNamespace(model_version=3, last_measurement_id=200),
        measurements=[measurement],
        profile_rows=[global_profile, selected_profile],
        snapshot_rows=[snapshot],
    )

    monkeypatch.setattr(vodomery_anomaly, "Session", lambda *args, **kwargs: session)

    inserted = vodomery_anomaly.score_new_measurements(
        model_version=3,
        batch_size=10,
        use_per_identifier_selection=False,
    )

    assert inserted == 1
    assert session.snapshot_select_count == 0
    assert session.insert_rows[0]["expected_mean"] == 10.0
    assert session.insert_rows[0]["model_version"] == 3


def test_vodomery_scoring_can_use_per_identifier_selected_profile(monkeypatch):
    global_profile = SimpleNamespace(
        model_version=3,
        identifikace="L1_V1",
        interval_minutes=15,
        day_of_week=3,
        slot=48,
        mean=10.0,
        std=2.0,
        median=10.0,
        p10=8.0,
        p90=12.0,
    )
    selected_profile = SimpleNamespace(
        model_version=2,
        identifikace="L1_V1",
        interval_minutes=15,
        day_of_week=3,
        slot=48,
        mean=16.0,
        std=1.0,
        median=16.0,
        p10=12.0,
        p90=20.0,
    )
    measurement = SimpleNamespace(
        id=202,
        identifikace="L1_V1",
        interval_minutes=15,
        day_of_week=3,
        slot=48,
        delta=17.0,
        date=datetime.datetime(2026, 7, 9, 12, 0),
    )
    snapshot = SimpleNamespace(
        identifier="L1_V1",
        selected_model_version=2,
        forecast_period_start=datetime.datetime(2026, 7, 6),
        forecast_period_end=datetime.datetime(2026, 7, 13),
    )
    session = FakeSession(
        state=SimpleNamespace(model_version=3, last_measurement_id=200),
        measurements=[measurement],
        profile_rows=[global_profile, selected_profile],
        snapshot_rows=[snapshot],
    )

    monkeypatch.setattr(vodomery_anomaly, "Session", lambda *args, **kwargs: session)

    inserted = vodomery_anomaly.score_new_measurements(
        model_version=3,
        batch_size=10,
        use_per_identifier_selection=True,
        selection_mode="dry_run",
    )

    assert inserted == 1
    assert session.snapshot_select_count == 1
    assert session.insert_rows == [
        {
            "measurement_id": 202,
            "identifikace": "L1_V1",
            "date": datetime.datetime(2026, 7, 9, 12, 0),
            "actual_value": 17.0,
            "expected_mean": 16.0,
            "expected_std": 1.0,
            "expected_median": 16.0,
            "expected_p10": 12.0,
            "expected_p90": 20.0,
            "deviation": 1.0,
            "z_score": 1.0,
            "is_anomaly": False,
            "severity": None,
            "model_version": 3,
        }
    ]


def test_plynomery_scoring_uses_conflict_safe_insert(monkeypatch):
    profile = SimpleNamespace(
        identifikace="P_A1",
        interval_minutes=15,
        day_of_week=1,
        slot=12,
        mean=1.0,
        std=0.25,
        median=0.9,
        p10=0.2,
        p90=1.5,
    )
    measurement = SimpleNamespace(
        id=456,
        identifikace="P_A1",
        interval_minutes=15,
        day_of_week=1,
        slot=12,
        delta=2.0,
        date=datetime.datetime(2026, 4, 21, 13, 30),
    )
    session = FakeSession(
        state=SimpleNamespace(model_version=1, last_measurement_id=100),
        measurements=[measurement],
        profile_rows=[profile],
    )

    monkeypatch.setattr(plynomery_anomaly, "Session", lambda *args, **kwargs: session)
    monkeypatch.setattr(plynomery_anomaly, "ensure_scoring_tables", lambda: None)

    inserted = plynomery_anomaly.score_new_measurements(model_version=1, batch_size=10)

    assert inserted == 1
    assert session.commit_calls == 1
    assert session.insert_rows == [
        {
            "measurement_id": 456,
            "identifikace": "P_A1",
            "date": datetime.datetime(2026, 4, 21, 13, 30),
            "actual_value": 2.0,
            "expected_mean": 1.0,
            "expected_std": 0.25,
            "expected_median": 0.9,
            "expected_p10": 0.2,
            "expected_p90": 1.5,
            "deviation": 1.0,
            "z_score": 4.0,
            "is_anomaly": True,
            "severity": "HIGH",
            "model_version": 1,
        }
    ]
    assert "ON CONFLICT (MEASUREMENT_ID, MODEL_VERSION) DO NOTHING" in _normalize_sql(
        session.insert_statement
    )
