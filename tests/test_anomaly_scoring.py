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
    def __init__(
        self,
        *,
        state,
        measurements,
        profile_rows=None,
        snapshot_rows=None,
        profile_rows_by_entity=None,
    ):
        self.state = state
        self.measurements = measurements
        self.profile_rows = profile_rows or []
        self.snapshot_rows = snapshot_rows or []
        self.profile_rows_by_entity = profile_rows_by_entity or {}
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
                plynomery_anomaly.PlynomeryWeatherModelProfile,
            ):
                return FakeScalarResult(
                    self.profile_rows_by_entity.get(entity, self.profile_rows)
                )
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


def test_vodomery_insufficient_history_snapshot_has_no_profile_version():
    measurement = SimpleNamespace(
        identifikace="NEW_V1",
        date=datetime.datetime(2026, 7, 29, 12, 0),
    )
    snapshot = SimpleNamespace(
        identifier="NEW_V1",
        selected_model_version=3,
        fallback_reason="insufficient_history",
        forecast_period_start=datetime.datetime(2026, 7, 27),
        forecast_period_end=datetime.datetime(2026, 8, 3),
    )

    model_version = vodomery_anomaly._profile_model_version_for_measurement(
        measurement,
        snapshots_by_identifier={"NEW_V1": [snapshot]},
        default_model_version=3,
    )

    assert model_version is None
    assert (
        vodomery_anomaly._selected_profile_versions({"NEW_V1": [snapshot]})
        == set()
    )


def test_vodomery_scoring_skips_unavailable_selection_and_advances_checkpoint(
    monkeypatch,
):
    measurement = SimpleNamespace(
        id=777,
        identifikace="NEW_V1",
        interval_minutes=15,
        day_of_week=2,
        slot=48,
        delta=0.1,
        date=datetime.datetime(2026, 7, 29, 12, 0),
    )
    global_profile = SimpleNamespace(
        model_version=3,
        identifikace="NEW_V1",
        interval_minutes=15,
        day_of_week=2,
        slot=48,
        mean=0.0,
        std=0.1,
        median=0.0,
        p10=0.0,
        p90=0.0,
    )
    snapshot = SimpleNamespace(
        identifier="NEW_V1",
        selected_model_version=3,
        fallback_reason="insufficient_history",
        forecast_period_start=datetime.datetime(2026, 7, 27),
        forecast_period_end=datetime.datetime(2026, 8, 3),
    )
    session = FakeSession(
        state=SimpleNamespace(model_version=3, last_measurement_id=700),
        measurements=[measurement],
        profile_rows=[global_profile],
        snapshot_rows=[snapshot],
    )
    monkeypatch.setattr(vodomery_anomaly, "Session", lambda *args, **kwargs: session)

    inserted = vodomery_anomaly.score_new_measurements(
        model_version=3,
        batch_size=10,
        use_per_identifier_selection=True,
    )

    assert inserted == 0
    assert session.insert_rows is None
    assert session.update_statement.compile().params["last_measurement_id"] == 777


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


def test_plynomery_weather_scoring_uses_hdd_adjusted_profile_and_checkpoint(monkeypatch):
    profile = SimpleNamespace(
        identifikace="P_A1",
        interval_minutes=15,
        day_of_week=1,
        slot=12,
        base_mean=1.0,
        hdd_slope=0.5,
        residual_std=0.25,
        residual_median=0.1,
        residual_p10=-0.2,
        residual_p90=0.4,
    )
    measurement = SimpleNamespace(
        id=457,
        identifikace="P_A1",
        interval_minutes=15,
        day_of_week=1,
        slot=12,
        delta=3.0,
        date=datetime.datetime(2026, 4, 21, 13, 45),
    )
    state = SimpleNamespace(model_version=2, last_measurement_id=100)
    session = FakeSession(
        state=state,
        measurements=[measurement],
        profile_rows=[profile],
    )

    monkeypatch.setattr(plynomery_anomaly, "Session", lambda *args, **kwargs: session)
    monkeypatch.setattr(plynomery_anomaly, "ensure_scoring_tables", lambda: None)
    monkeypatch.setattr(
        plynomery_anomaly,
        "_load_hdd_24h_by_measurement_id",
        lambda _session, measurements: {measurements[0].id: 4.0},
    )

    inserted = plynomery_anomaly.score_new_measurements(model_version=2, batch_size=10)

    assert inserted == 1
    assert session.commit_calls == 1
    assert session.insert_rows == [
        {
            "measurement_id": 457,
            "identifikace": "P_A1",
            "date": datetime.datetime(2026, 4, 21, 13, 45),
            "actual_value": 3.0,
            "expected_mean": 3.0,
            "expected_std": 0.25,
            "expected_median": 3.1,
            "expected_p10": 2.8,
            "expected_p90": 3.4,
            "deviation": 0.0,
            "z_score": 0.0,
            "is_anomaly": False,
            "severity": None,
            "model_version": 2,
        }
    ]
    assert session.update_statement is not None


def test_plynomery_snapshot_lookup_uses_explicit_mode_and_deterministic_precedence():
    measurement = SimpleNamespace(
        id=501,
        identifikace="P_A1",
        date=datetime.datetime(2026, 7, 29, 12, 0),
    )
    older_period = SimpleNamespace(
        id=10,
        identifier="P_A1",
        selected_model_version=1,
        fallback_reason="none",
        forecast_period_start=datetime.datetime(2026, 7, 20),
        forecast_period_end=datetime.datetime(2026, 8, 3),
        created_at=datetime.datetime(2026, 7, 20, 6, 10),
    )
    newer_period = SimpleNamespace(
        id=11,
        identifier="P_A1",
        selected_model_version=2,
        fallback_reason="none",
        forecast_period_start=datetime.datetime(2026, 7, 27),
        forecast_period_end=datetime.datetime(2026, 8, 3),
        created_at=datetime.datetime(2026, 7, 27, 6, 10),
    )
    session = FakeSession(
        state=None,
        measurements=[measurement],
        snapshot_rows=[older_period, newer_period],
    )

    snapshots = plynomery_anomaly._load_selected_model_snapshots(
        session,
        measurements=[measurement],
        selection_mode="dry_run",
    )
    selection = plynomery_anomaly._resolve_profile_selection_for_measurement(
        measurement,
        snapshots_by_identifier=snapshots,
    )

    assert session.snapshot_select_count == 1
    assert [row.id for row in snapshots["P_A1"]] == [11, 10]
    assert selection.model_version == 2
    assert selection.prediction_available is True
    assert selection.snapshot is newer_period


def test_plynomery_snapshot_lookup_marks_insufficient_history_unavailable():
    measurement = SimpleNamespace(
        identifikace="P_NEW",
        date=datetime.datetime(2026, 7, 29, 12, 0),
    )
    unavailable_snapshot = SimpleNamespace(
        id=12,
        identifier="P_NEW",
        selected_model_version=2,
        fallback_reason="insufficient_history",
        forecast_period_start=datetime.datetime(2026, 7, 27),
        forecast_period_end=datetime.datetime(2026, 8, 3),
        created_at=datetime.datetime(2026, 7, 27, 6, 10),
    )

    selection = plynomery_anomaly._resolve_profile_selection_for_measurement(
        measurement,
        snapshots_by_identifier={"P_NEW": [unavailable_snapshot]},
    )

    assert selection.model_version is None
    assert selection.prediction_available is False
    assert selection.fallback_reason == "insufficient_history"
    assert (
        plynomery_anomaly._selected_profile_versions(
            {"P_NEW": [unavailable_snapshot]}
        )
        == set()
    )


def test_plynomery_selected_profile_loaders_are_identifier_scoped():
    class CapturingSession:
        def __init__(self):
            self.statements = []

        def execute(self, statement):
            self.statements.append(statement)
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [])
            )

    session = CapturingSession()
    plynomery_anomaly._load_static_profiles(
        session,
        {1},
        identifiers={"P_STATIC"},
    )
    plynomery_anomaly._load_weather_profiles(
        session,
        identifiers={"P_WEATHER"},
    )

    static_sql = _normalize_sql(session.statements[0])
    weather_sql = _normalize_sql(session.statements[1])
    assert "IDENTIFIKACE IN" in static_sql
    assert "IDENTIFIKACE IN" in weather_sql


def test_plynomery_snapshot_lookup_uses_recorded_global_fallback():
    measurement = SimpleNamespace(
        identifikace="P_A1",
        date=datetime.datetime(2026, 7, 29, 12, 0),
    )
    fallback_snapshot = SimpleNamespace(
        id=14,
        identifier="P_A1",
        selected_model_version=2,
        fallback_reason="below_coverage_threshold",
        forecast_period_start=datetime.datetime(2026, 7, 27),
        forecast_period_end=datetime.datetime(2026, 8, 3),
        created_at=datetime.datetime(2026, 7, 27, 6, 10),
    )

    selection = plynomery_anomaly._resolve_profile_selection_for_measurement(
        measurement,
        snapshots_by_identifier={"P_A1": [fallback_snapshot]},
    )

    assert selection.model_version == 2
    assert selection.prediction_available is True
    assert selection.fallback_reason == "below_coverage_threshold"


def test_plynomery_snapshot_lookup_is_unavailable_outside_snapshot_period():
    measurement = SimpleNamespace(
        identifikace="P_A1",
        date=datetime.datetime(2026, 8, 3, 0, 0),
    )
    ended_snapshot = SimpleNamespace(
        id=13,
        identifier="P_A1",
        selected_model_version=1,
        fallback_reason="none",
        forecast_period_start=datetime.datetime(2026, 7, 27),
        forecast_period_end=datetime.datetime(2026, 8, 3),
        created_at=datetime.datetime(2026, 7, 27, 6, 10),
    )

    selection = plynomery_anomaly._resolve_profile_selection_for_measurement(
        measurement,
        snapshots_by_identifier={"P_A1": [ended_snapshot]},
    )

    assert selection.model_version is None
    assert selection.prediction_available is False
    assert selection.fallback_reason == "no_selection_snapshot"


def test_plynomery_mixed_scoring_uses_selected_profiles_and_advances_unavailable(
    monkeypatch,
):
    measurement_date = datetime.datetime(2026, 7, 29, 12, 0)
    measurements = [
        SimpleNamespace(
            id=601,
            identifikace="P_STATIC",
            interval_minutes=15,
            day_of_week=2,
            slot=48,
            delta=2.0,
            date=measurement_date,
        ),
        SimpleNamespace(
            id=602,
            identifikace="P_WEATHER",
            interval_minutes=15,
            day_of_week=2,
            slot=48,
            delta=3.0,
            date=measurement_date,
        ),
        SimpleNamespace(
            id=603,
            identifikace="P_NEW",
            interval_minutes=15,
            day_of_week=2,
            slot=48,
            delta=1.0,
            date=measurement_date,
        ),
        SimpleNamespace(
            id=604,
            identifikace="P_NO_SNAPSHOT",
            interval_minutes=15,
            day_of_week=2,
            slot=48,
            delta=1.0,
            date=measurement_date,
        ),
    ]
    snapshots = [
        SimpleNamespace(
            id=21,
            identifier="P_STATIC",
            selected_model_version=1,
            fallback_reason="none",
            forecast_period_start=datetime.datetime(2026, 7, 27),
            forecast_period_end=datetime.datetime(2026, 8, 3),
            created_at=datetime.datetime(2026, 7, 27, 6, 10),
        ),
        SimpleNamespace(
            id=22,
            identifier="P_WEATHER",
            selected_model_version=2,
            fallback_reason="none",
            forecast_period_start=datetime.datetime(2026, 7, 27),
            forecast_period_end=datetime.datetime(2026, 8, 3),
            created_at=datetime.datetime(2026, 7, 27, 6, 10),
        ),
        SimpleNamespace(
            id=23,
            identifier="P_NEW",
            selected_model_version=2,
            fallback_reason="insufficient_history",
            forecast_period_start=datetime.datetime(2026, 7, 27),
            forecast_period_end=datetime.datetime(2026, 8, 3),
            created_at=datetime.datetime(2026, 7, 27, 6, 10),
        ),
    ]
    static_profile = SimpleNamespace(
        model_version=1,
        identifikace="P_STATIC",
        interval_minutes=15,
        day_of_week=2,
        slot=48,
        mean=1.0,
        std=0.5,
        median=1.0,
        p10=0.5,
        p90=1.5,
    )
    weather_profile = SimpleNamespace(
        model_version=2,
        identifikace="P_WEATHER",
        interval_minutes=15,
        day_of_week=2,
        slot=48,
        base_mean=1.0,
        hdd_slope=0.5,
        residual_std=0.25,
        residual_median=0.1,
        residual_p10=-0.2,
        residual_p90=0.4,
    )
    session = FakeSession(
        state=SimpleNamespace(model_version=2, last_measurement_id=600),
        measurements=measurements,
        snapshot_rows=snapshots,
        profile_rows_by_entity={
            plynomery_anomaly.PlynomeryProfilesAnomaly: [static_profile],
            plynomery_anomaly.PlynomeryWeatherModelProfile: [weather_profile],
        },
    )
    hdd_measurement_ids = []

    monkeypatch.setattr(plynomery_anomaly, "Session", lambda *args, **kwargs: session)
    monkeypatch.setattr(plynomery_anomaly, "ensure_scoring_tables", lambda: None)
    monkeypatch.setattr(
        plynomery_anomaly,
        "_load_hdd_24h_by_measurement_id",
        lambda _session, rows: (
            hdd_measurement_ids.extend(row.id for row in rows)
            or {602: 4.0}
        ),
    )

    inserted = plynomery_anomaly.score_new_measurements(
        model_version=2,
        batch_size=10,
        use_per_identifier_selection=True,
        selection_mode="dry_run",
    )

    assert inserted == 2
    assert hdd_measurement_ids == [602]
    assert [row["measurement_id"] for row in session.insert_rows] == [601, 602]
    assert [row["expected_mean"] for row in session.insert_rows] == [1.0, 3.0]
    assert {row["model_version"] for row in session.insert_rows} == {2}
    assert session.update_statement.compile().params["last_measurement_id"] == 604
    assert session.commit_calls == 1


def test_plynomery_per_identifier_lookup_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(
        plynomery_anomaly,
        "config",
        lambda *args, **kwargs: kwargs["default"],
    )

    assert (
        plynomery_anomaly._per_identifier_selection_enabled(
            SimpleNamespace(),
            model_version=2,
            use_per_identifier_selection=None
        )
        is False
    )
    assert (
        plynomery_anomaly._per_identifier_selection_enabled(
            SimpleNamespace(),
            model_version=2,
            use_per_identifier_selection=True
        )
        is True
    )


def test_plynomery_per_identifier_lookup_only_enables_active_candidate(monkeypatch):
    monkeypatch.setattr(
        plynomery_anomaly,
        "config",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        plynomery_anomaly,
        "get_runtime_model_version",
        lambda *, session, default: 2,
    )
    session = SimpleNamespace()

    assert (
        plynomery_anomaly._per_identifier_selection_enabled(
            session,
            model_version=1,
            use_per_identifier_selection=None,
        )
        is False
    )
    assert (
        plynomery_anomaly._per_identifier_selection_enabled(
            session,
            model_version=2,
            use_per_identifier_selection=None,
        )
        is True
    )
