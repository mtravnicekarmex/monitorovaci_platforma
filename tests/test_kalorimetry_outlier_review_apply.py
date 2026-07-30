from datetime import datetime
from types import SimpleNamespace

from moduly.mereni.kalorimetry.database import outlier_review_apply


class Result:
    def __init__(self, *, scalar=None, rows=None):
        self.scalar = scalar
        self.rows = rows or []

    def scalar_one(self):
        return self.scalar

    def scalars(self):
        return self

    def all(self):
        return self.rows


def test_active_score_repair_is_noop_before_scoring_activation():
    class Session:
        def __init__(self):
            self.calls = 0

        def execute(self, statement):
            self.calls += 1
            return Result(scalar=None)

    session = Session()

    rebuilt = outlier_review_apply._rebuild_active_scores_if_enabled(
        session,
        identifikace="KAL-01",
        start_date=datetime(2026, 4, 20),
    )

    assert rebuilt == 0
    assert session.calls == 1


def test_active_score_repair_deletes_and_rebuilds_period_valid_stream(
    monkeypatch,
):
    measurements = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

    class Session:
        def __init__(self):
            self.calls = 0

        def execute(self, statement):
            self.calls += 1
            if self.calls == 1:
                return Result(scalar="monitoring.kalorimetry_anomaly_scores")
            if self.calls == 2:
                return Result()
            return Result(rows=measurements)

    captured = {}
    monkeypatch.setattr(
        outlier_review_apply,
        "rebuild_active_scores_for_measurements",
        lambda session, *, measurements: captured.setdefault(
            "measurements",
            measurements,
        )
        and len(measurements),
    )
    session = Session()

    rebuilt = outlier_review_apply._rebuild_active_scores_if_enabled(
        session,
        identifikace="KAL-01",
        start_date=datetime(2026, 4, 20),
    )

    assert rebuilt == 2
    assert captured["measurements"] == measurements
    assert session.calls == 3
