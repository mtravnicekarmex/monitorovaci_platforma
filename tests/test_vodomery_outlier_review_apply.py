import datetime
from types import SimpleNamespace

from moduly.mereni.vodomery.database import outlier_review_apply
from moduly.mereni.vodomery import vodomery_anomaly


def test_review_rebuild_uses_selection_only_for_active_model(monkeypatch):
    score_calls = []
    event_calls = []
    monkeypatch.setattr(
        outlier_review_apply,
        "_rebuild_measurements_for_review",
        lambda *_args: {"inserted_actual_rows": 1},
    )
    monkeypatch.setattr(
        outlier_review_apply,
        "get_runtime_model_version",
        lambda *, session: 2,
    )
    monkeypatch.setattr(
        outlier_review_apply,
        "get_candidate_model_versions",
        lambda: (1, 2),
    )
    monkeypatch.setattr(
        outlier_review_apply,
        "_rebuild_scores_for_ident",
        lambda _session, **kwargs: score_calls.append(kwargs) or kwargs,
    )
    monkeypatch.setattr(
        outlier_review_apply,
        "_rebuild_events_for_ident",
        lambda _session, **kwargs: event_calls.append(kwargs) or kwargs,
    )

    result = outlier_review_apply._rebuild_after_review_update(
        object(),
        SimpleNamespace(
            identifikace="V1",
            date=datetime.datetime(2026, 7, 27),
        ),
    )

    assert [
        (call["model_version"], call["use_per_identifier_selection"])
        for call in score_calls
    ] == [(1, False), (2, True)]
    assert [call["model_version"] for call in event_calls] == [1, 2]
    assert len(result["scores"]) == 2


def test_active_review_score_rebuild_uses_shared_selected_builder(monkeypatch):
    measurement = SimpleNamespace(id=10)
    selected_row = {"measurement_id": 10, "model_version": 2}

    class FakeSession:
        def __init__(self):
            self.executed = []

        def execute(self, statement, params=None):
            self.executed.append((statement, params))
            return SimpleNamespace()

    session = FakeSession()
    monkeypatch.setattr(
        outlier_review_apply,
        "_load_measurements_for_score_rebuild",
        lambda *_args, **_kwargs: [measurement],
    )
    captured = {}

    def build_selected(_session, **kwargs):
        captured.update(kwargs)
        return [selected_row]

    monkeypatch.setattr(
        outlier_review_apply,
        "_build_per_identifier_selected_score_rows",
        build_selected,
    )

    result = outlier_review_apply._rebuild_scores_for_ident(
        session,
        identifikace="V1",
        model_version=2,
        start_date=datetime.datetime(2026, 7, 27),
        use_per_identifier_selection=True,
    )

    assert captured == {
        "measurements": [measurement],
        "output_model_version": 2,
    }
    assert result == {
        "model_version": 2,
        "inserted_scores": 1,
        "profile_source": "active_per_identifier_selection",
    }
    assert len(session.executed) == 2


def test_non_active_review_rebuild_retains_candidate_profile():
    profile = SimpleNamespace(
        identifikace="V1",
        interval_minutes=15,
        day_of_week=0,
        slot=8,
        mean=1.0,
        std=0.5,
        median=1.0,
        p10=0.5,
        p90=1.5,
    )
    measurement = SimpleNamespace(
        id=10,
        identifikace="V1",
        date=datetime.datetime(2026, 7, 27, 2),
        interval_minutes=15,
        day_of_week=0,
        slot=8,
        delta=2.0,
    )

    class Result:
        def __init__(self, rows=None):
            self.rows = rows or []

        def scalars(self):
            return self

        def all(self):
            return self.rows

    class FakeSession:
        def __init__(self):
            self.results = [
                Result(),
                Result([profile]),
                Result([measurement]),
                Result(),
            ]

        def execute(self, _statement, _params=None):
            return self.results.pop(0)

    result = outlier_review_apply._rebuild_scores_for_ident(
        FakeSession(),
        identifikace="V1",
        model_version=1,
        start_date=datetime.datetime(2026, 7, 27),
        use_per_identifier_selection=False,
    )

    assert result == {"model_version": 1, "inserted_scores": 1}


def test_active_selected_builder_does_not_fallback_without_selection(
    monkeypatch,
):
    measurement = SimpleNamespace(
        id=10,
        identifikace="V1",
        date=datetime.datetime(2026, 7, 27, 2),
        interval_minutes=15,
        day_of_week=0,
        slot=8,
        delta=2.0,
    )
    monkeypatch.setattr(
        vodomery_anomaly,
        "_load_selected_model_snapshots",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        vodomery_anomaly,
        "_load_profiles",
        lambda *_args, **_kwargs: [],
    )

    assert vodomery_anomaly._build_per_identifier_selected_score_rows(
        object(),
        measurements=[measurement],
        output_model_version=2,
    ) == []
