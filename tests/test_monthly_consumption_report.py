import datetime
import math
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery.reporting import monthly_consumption_report as report_module


class _ScalarResult:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


class _RowsResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _FakeConnection:
    def __init__(self, period):
        self.period = period
        self.executed_sql = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.executed_sql.append(sql)
        if "SELECT DISTINCT identifikace" in sql:
            assert 'monitoring."Mereni_vodomery_vse"' in sql
            assert 'evidence."vodoměry"' not in sql
            assert params == {"period_end": self.period.period_end}
            return _ScalarResult(["A_V1", "B_V1"])

        cutoff = params["cutoff"]
        if cutoff == self.period.period_start:
            return _RowsResult([("A_V1", 100.0)])
        if cutoff == self.period.period_end:
            return _RowsResult([("A_V1", 112.5), ("B_V1", 205.0)])
        raise AssertionError(f"Unexpected cutoff: {cutoff!r}")


class _FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return self

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_build_monthly_report_dataframe_loads_devices_from_measurements(monkeypatch):
    period = report_module.ReportPeriod(
        year=2026,
        month=6,
        period_start=datetime.datetime(2026, 6, 1, 0, 0, 0),
        period_end=datetime.datetime(2026, 7, 1, 0, 0, 0),
    )
    connection = _FakeConnection(period)
    monkeypatch.setattr(report_module, "ENGINE_PG", _FakeEngine(connection))

    df = report_module._build_monthly_report_dataframe(period)

    assert [row["identifikace"] for row in df.to_dict(orient="records")] == ["A_V1", "B_V1"]
    row_a, row_b = df.to_dict(orient="records")
    assert row_a["počáteční stav měsíce"] == 100.0
    assert row_a["konečný stav měsíce"] == 112.5
    assert row_a["spotřeba"] == 12.5
    assert math.isnan(row_b["počáteční stav měsíce"])
    assert row_b["konečný stav měsíce"] == 205.0
    assert math.isnan(row_b["spotřeba"])
    assert any('monitoring."Mereni_vodomery_vse"' in sql for sql in connection.executed_sql)
    assert not any('evidence."vodoměry"' in sql for sql in connection.executed_sql)
