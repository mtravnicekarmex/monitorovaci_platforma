import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from moduly.mereni.plynomery.branches import (
    PLYNOMERY_BRANCH_CONFIGS,
    PlynomeryBranchConfig,
    PlynomeryMeterNode,
    get_plynomery_branch_config,
)
from moduly.mereni.plynomery.database.models import PlynomeryFakturacniOdecet
from moduly.mereni.plynomery.reporting.monthly_billing_report import (
    build_monthly_plynomery_billing_report_html,
)
from services.api.services import plynomery_billing
from services.api.services.plynomery_billing import (
    BranchBillingSummary,
    BranchDeviceConsumption,
    BillingReadingInput,
    BillingReadingRecord,
    MeterSnapshot,
    MonthlyBillingReportData,
    PlynomeryBillingError,
    _build_branch_summary,
    _latest_billing_rows_by_identifikace,
    _normalize_reading_input,
    build_monthly_billing_report_data,
    load_latest_previous_billing_readings,
    upsert_billing_readings,
    validate_monthly_billing_report_inputs,
)


def test_plynomery_billing_reading_table_is_prediction_isolated():
    table = PlynomeryFakturacniOdecet.__table__

    assert table.schema == "monitoring"
    assert table.name == "plynomery_fakturacni_odecty"
    assert not table.foreign_keys

    assert {
        "id",
        "identifikace",
        "period_start",
        "period_end",
        "reading_at",
        "objem",
        "source",
        "entered_by",
        "note",
        "created_at",
        "updated_at",
    }.issubset(table.c.keys())

    constraint_names = {constraint.name for constraint in table.constraints}
    assert "uq_plynomery_fakturacni_odecty_period" not in constraint_names
    assert "ck_plynomery_fakturacni_odecty_period_order" in constraint_names
    assert "ck_plynomery_fakturacni_odecty_objem_non_negative" in constraint_names

    index_names = {index.name for index in table.indexes}
    assert "ix_plynomery_fakturacni_odecty_ident_period_end" in index_names


def test_latest_billing_rows_prefers_latest_reading_time_then_latest_correction():
    earlier_reading_saved_later = datetime.datetime(2026, 7, 1, 8, 0)
    later_reading_saved_earlier = datetime.datetime(2026, 8, 1, 8, 0)
    rows = [
        SimpleNamespace(
            id=3,
            identifikace="INNOGY_A",
            reading_at=earlier_reading_saved_later,
            created_at=datetime.datetime(2026, 8, 7, 10, 0),
        ),
        SimpleNamespace(
            id=1,
            identifikace="INNOGY_A",
            reading_at=later_reading_saved_earlier,
            created_at=datetime.datetime(2026, 8, 7, 9, 0),
        ),
        SimpleNamespace(
            id=4,
            identifikace="INNOGY_B",
            reading_at=later_reading_saved_earlier,
            created_at=datetime.datetime(2026, 8, 7, 9, 0),
        ),
        SimpleNamespace(
            id=5,
            identifikace="INNOGY_B",
            reading_at=later_reading_saved_earlier,
            created_at=datetime.datetime(2026, 8, 7, 10, 0),
        ),
    ]

    latest = _latest_billing_rows_by_identifikace(rows)

    assert [row.id for row in latest] == [1, 5]


def test_previous_billing_reading_lookup_uses_start_day_reading_time_not_period_end(monkeypatch):
    config = PlynomeryBranchConfig(
        key="TEST_A",
        title="Test A",
        billing_ident="INNOGY_A",
        submeters=(),
    )
    period_start = datetime.datetime(2026, 7, 1)
    returned_row = SimpleNamespace(
        id=10,
        identifikace="INNOGY_A",
        period_start=datetime.datetime(2026, 7, 1),
        period_end=datetime.datetime(2026, 8, 1),
        reading_at=period_start,
        objem=100.0,
        source="manual",
        entered_by="tester",
        note=None,
        created_at=datetime.datetime(2026, 8, 7, 10, 0),
        updated_at=datetime.datetime(2026, 8, 7, 10, 0),
    )
    captured_filters: list[str] = []
    captured_ordering: list[str] = []

    class FakeQuery:
        def filter(self, *conditions):
            captured_filters.extend(
                str(
                    condition.compile(
                        dialect=postgresql.dialect(),
                        compile_kwargs={"literal_binds": True},
                    )
                )
                for condition in conditions
            )
            return self

        def order_by(self, *columns):
            captured_ordering.extend(
                str(column.compile(dialect=postgresql.dialect()))
                for column in columns
            )
            return self

        def first(self):
            return returned_row

    class FakeSession:
        def query(self, _model):
            return FakeQuery()

        def close(self):
            pass

    monkeypatch.setattr(plynomery_billing, "ensure_billing_readings_table", lambda: None)
    monkeypatch.setattr(plynomery_billing, "PLYNOMERY_BRANCH_CONFIGS", (config,))
    monkeypatch.setattr(plynomery_billing, "get_session_pg", lambda: FakeSession())

    result = load_latest_previous_billing_readings(period_start)

    assert result["INNOGY_A"].reading_at == period_start
    assert any("reading_at <" in condition for condition in captured_filters)
    assert not any("period_end <=" in condition for condition in captured_filters)
    assert captured_ordering[0].endswith("reading_at DESC")


def test_billing_reading_save_is_append_only_insert(monkeypatch):
    executed_sql: list[str] = []

    class FakeResult:
        rowcount = 1

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_exc_info):
            return False

        def execute(self, statement):
            executed_sql.append(
                str(statement.compile(dialect=postgresql.dialect()))
            )
            return FakeResult()

        def commit(self):
            pass

    monkeypatch.setattr(plynomery_billing, "ensure_billing_readings_table", lambda: None)
    monkeypatch.setattr(plynomery_billing, "Session", lambda _engine: FakeSession())

    saved_count = upsert_billing_readings(
        (
            BillingReadingInput(
                identifikace="INNOGY_A",
                period_start=datetime.datetime(2026, 7, 1),
                period_end=datetime.datetime(2026, 8, 1),
                reading_at=datetime.datetime(2026, 8, 1, 8, 0),
                objem=123.0,
                entered_by="tester",
                note="novy radek",
            ),
        )
    )

    assert saved_count == 1
    assert len(executed_sql) == 1
    assert "INSERT INTO" in executed_sql[0]
    assert "ON CONFLICT" not in executed_sql[0]


def test_plynomery_branch_config_matches_static_billing_meters():
    assert tuple(config.billing_ident for config in PLYNOMERY_BRANCH_CONFIGS) == (
        "INNOGY_A",
        "INNOGY_B",
        "INNOGY_E",
        "INNOGY_F",
        "INNOGY_G",
        "INNOGY_K",
        "INNOGY_L",
    )

    innogy_b = get_plynomery_branch_config("INNOGY_B")
    assert innogy_b.direct_submeter_idents == ("Bk_P1",)
    assert innogy_b.residual_label == "Budova B - zbytek po odečtení Bk_P1"

    innogy_l = get_plynomery_branch_config("INNOGY_L")
    assert innogy_l.direct_submeter_idents == (
        "L1_P1",
        "L5_P1",
        "L6_P1",
        "L2-L3_P8",
    )
    assert innogy_l.all_submeter_idents == (
        "L1_P1",
        "L5_P1",
        "L6_P1",
        "L2-L3_P8",
        "L2-L3_P1",
        "L2-L3_P2",
        "L2-L3_P3",
        "L2-L3_P4",
        "L2-L3_P5",
        "L2-L3_P7",
    )


def _reading(
    *,
    identifikace: str,
    objem: float,
    reading_at: datetime.datetime,
) -> BillingReadingRecord:
    return BillingReadingRecord(
        id=1,
        identifikace=identifikace,
        period_start=datetime.datetime(2026, 7, 1),
        period_end=datetime.datetime(2026, 8, 1),
        reading_at=reading_at,
        objem=objem,
        source="manual",
        entered_by="tester",
        note=None,
        created_at=reading_at,
        updated_at=reading_at,
    )


def test_billing_reading_input_rejects_non_finite_volume():
    with pytest.raises(PlynomeryBillingError):
        _normalize_reading_input(
            BillingReadingInput(
                identifikace="INNOGY_A",
                period_start=datetime.datetime(2026, 7, 1),
                period_end=datetime.datetime(2026, 8, 1),
                reading_at=datetime.datetime(2026, 8, 1),
                objem=float("nan"),
            )
        )


def test_billing_reading_input_normalizes_timezone_and_text_fields():
    normalized = _normalize_reading_input(
        BillingReadingInput(
            identifikace="INNOGY_A",
            period_start=datetime.datetime(2026, 7, 1),
            period_end=datetime.datetime(2026, 8, 1),
            reading_at=datetime.datetime(
                2026,
                8,
                1,
                0,
                30,
                tzinfo=datetime.UTC,
            ),
            objem=123.456,
            entered_by=" tester ",
            note=" poznamka ",
        )
    )

    assert normalized["reading_at"] == datetime.datetime(2026, 8, 1, 2, 30)
    assert normalized["entered_by"] == "tester"
    assert normalized["note"] == "poznamka"


def test_monthly_billing_report_inputs_require_current_previous_and_non_decreasing_readings():
    period_start = datetime.datetime(2026, 7, 1)
    period_end = datetime.datetime(2026, 8, 1)
    current_readings = {
        "INNOGY_A": _reading(
            identifikace="INNOGY_A",
            objem=90.0,
            reading_at=period_end,
        ),
        "INNOGY_B": _reading(
            identifikace="INNOGY_B",
            objem=150.0,
            reading_at=period_end,
        ),
    }
    previous_readings = {
        "INNOGY_A": _reading(
            identifikace="INNOGY_A",
            objem=100.0,
            reading_at=period_start,
        )
    }

    issues = validate_monthly_billing_report_inputs(
        current_readings=current_readings,
        previous_readings=previous_readings,
    )

    issues_by_ident = {issue.identifikace: issue.issue_type for issue in issues}
    assert issues_by_ident["INNOGY_A"] == "reading_decreased"
    assert issues_by_ident["INNOGY_B"] == "missing_previous"
    assert issues_by_ident["INNOGY_E"] == "missing_current"


def test_monthly_billing_report_inputs_reject_non_forward_reading_interval():
    reading_time = datetime.datetime(2026, 8, 1, 8, 0)
    current_readings = {
        "INNOGY_A": _reading(
            identifikace="INNOGY_A",
            objem=120.0,
            reading_at=reading_time,
        )
    }
    previous_readings = {
        "INNOGY_A": _reading(
            identifikace="INNOGY_A",
            objem=100.0,
            reading_at=reading_time,
        )
    }

    issues = validate_monthly_billing_report_inputs(
        current_readings=current_readings,
        previous_readings=previous_readings,
    )

    innogy_a_issue = next(issue for issue in issues if issue.identifikace == "INNOGY_A")
    assert innogy_a_issue.issue_type == "reading_time_not_after_previous"


def test_monthly_report_uses_billing_reading_times_for_submeter_cutoffs(monkeypatch):
    config = PlynomeryBranchConfig(
        key="TEST_B",
        title="Test B",
        billing_ident="INNOGY_B",
        submeters=(PlynomeryMeterNode("Bk_P1"),),
    )
    previous_time = datetime.datetime(2026, 7, 2, 6, 30)
    current_time = datetime.datetime(2026, 8, 3, 10, 15)
    previous = _reading(
        identifikace="INNOGY_B",
        objem=100.0,
        reading_at=previous_time,
    )
    current = _reading(
        identifikace="INNOGY_B",
        objem=150.0,
        reading_at=current_time,
    )
    cutoff_calls: list[tuple[tuple[str, ...], datetime.datetime]] = []

    monkeypatch.setattr(
        plynomery_billing,
        "PLYNOMERY_BRANCH_CONFIGS",
        (config,),
    )
    monkeypatch.setattr(
        plynomery_billing,
        "list_billing_readings_for_period",
        lambda _period_start, _period_end: (current,),
    )
    monkeypatch.setattr(
        plynomery_billing,
        "load_latest_previous_billing_readings",
        lambda _period_start: {"INNOGY_B": previous},
    )

    def fake_load_snapshots(
        identifiers: tuple[str, ...],
        cutoff: datetime.datetime,
    ) -> dict[str, MeterSnapshot]:
        cutoff_calls.append((identifiers, cutoff))
        value = 10.0 if cutoff == previous_time else 25.0
        return {"Bk_P1": MeterSnapshot("Bk_P1", value, cutoff)}

    monkeypatch.setattr(
        plynomery_billing,
        "load_last_valid_measurements_at_or_before",
        fake_load_snapshots,
    )

    report = build_monthly_billing_report_data(year=2026, month=7)

    assert cutoff_calls == [
        (("Bk_P1",), previous_time),
        (("Bk_P1",), current_time),
    ]
    branch = report.branches[0]
    assert branch.billing_consumption == 50.0
    assert branch.submeter_consumption_total == 15.0
    assert branch.device_rows[0].start_measured_at == previous_time
    assert branch.device_rows[0].end_measured_at == current_time


def test_innogy_l_branch_summary_does_not_double_count_nested_submeters():
    config = get_plynomery_branch_config("INNOGY_L")
    start_time = datetime.datetime(2026, 7, 1)
    end_time = datetime.datetime(2026, 8, 1)
    current_readings = {
        "INNOGY_L": _reading(
            identifikace="INNOGY_L",
            objem=200.0,
            reading_at=end_time,
        )
    }
    previous_readings = {
        "INNOGY_L": _reading(
            identifikace="INNOGY_L",
            objem=180.0,
            reading_at=start_time,
        )
    }
    start_snapshots = {
        "L1_P1": MeterSnapshot("L1_P1", 10.0, start_time),
        "L5_P1": MeterSnapshot("L5_P1", 20.0, start_time),
        "L6_P1": MeterSnapshot("L6_P1", 30.0, start_time),
        "L2-L3_P8": MeterSnapshot("L2-L3_P8", 100.0, start_time),
        "L2-L3_P1": MeterSnapshot("L2-L3_P1", 5.0, start_time),
        "L2-L3_P2": MeterSnapshot("L2-L3_P2", 2.0, start_time),
        "L2-L3_P3": MeterSnapshot("L2-L3_P3", 1.0, start_time),
        "L2-L3_P4": MeterSnapshot("L2-L3_P4", 4.0, start_time),
        "L2-L3_P5": MeterSnapshot("L2-L3_P5", 6.0, start_time),
        "L2-L3_P7": MeterSnapshot("L2-L3_P7", 7.0, start_time),
    }
    end_snapshots = {
        "L1_P1": MeterSnapshot("L1_P1", 12.0, end_time),
        "L5_P1": MeterSnapshot("L5_P1", 23.0, end_time),
        "L6_P1": MeterSnapshot("L6_P1", 31.0, end_time),
        "L2-L3_P8": MeterSnapshot("L2-L3_P8", 110.0, end_time),
        "L2-L3_P1": MeterSnapshot("L2-L3_P1", 12.0, end_time),
        "L2-L3_P2": MeterSnapshot("L2-L3_P2", 3.0, end_time),
        "L2-L3_P3": MeterSnapshot("L2-L3_P3", 3.0, end_time),
        "L2-L3_P4": MeterSnapshot("L2-L3_P4", 4.5, end_time),
        "L2-L3_P5": MeterSnapshot("L2-L3_P5", 6.25, end_time),
        "L2-L3_P7": MeterSnapshot("L2-L3_P7", 7.25, end_time),
    }

    summary = _build_branch_summary(
        config,
        current_readings=current_readings,
        previous_readings=previous_readings,
        period_start=start_time,
        period_end=end_time,
        start_snapshots=start_snapshots,
        end_snapshots=end_snapshots,
    )

    assert summary.billing_consumption == 20.0
    assert summary.submeter_consumption_total == 16.0
    assert summary.difference_vs_submeters == 4.0

    nested_row = next(row for row in summary.device_rows if row.identifikace == "L2-L3_P1")
    assert nested_row.consumption == 7.0
    assert nested_row.included_in_branch_sum is False
    assert nested_row.branch_share_percent == 35.0

    control_row = next(row for row in summary.device_rows if row.identifikace == "L2-L3_P8")
    assert control_row.included_in_branch_sum is True
    assert control_row.branch_share_percent == 50.0
    assert control_row.child_submeter_count == 6
    assert control_row.missing_child_submeter_count == 0
    assert control_row.child_submeter_consumption_total == 11.0
    assert control_row.child_submeter_difference == -1.0


def test_monthly_plynomery_billing_report_html_contains_manual_report_sections():
    branch = _build_branch_summary(
        get_plynomery_branch_config("INNOGY_B"),
        current_readings={
            "INNOGY_B": _reading(
                identifikace="INNOGY_B",
                objem=150.0,
                reading_at=datetime.datetime(2026, 8, 1),
            )
        },
        previous_readings={
            "INNOGY_B": _reading(
                identifikace="INNOGY_B",
                objem=100.0,
                reading_at=datetime.datetime(2026, 7, 1),
            )
        },
        period_start=datetime.datetime(2026, 7, 1),
        period_end=datetime.datetime(2026, 8, 1),
        start_snapshots={"Bk_P1": MeterSnapshot("Bk_P1", 40.0, datetime.datetime(2026, 7, 1))},
        end_snapshots={"Bk_P1": MeterSnapshot("Bk_P1", 55.0, datetime.datetime(2026, 8, 1))},
    )
    report = MonthlyBillingReportData(
        generated_at=datetime.datetime(2026, 8, 2, 9, 0),
        period_start=datetime.datetime(2026, 7, 1),
        period_end=datetime.datetime(2026, 8, 1),
        year=2026,
        month=7,
        branches=(branch,),
    )

    html = build_monthly_plynomery_billing_report_html(report)

    assert "Měsíční report fakturačních plynoměrů" in html
    assert "INNOGY_B" in html
    assert "Budova B - zbytek po odečtení Bk_P1" in html
    assert "+35.000 m³" in html
    assert 'class="page-header"' in html
    assert 'class="page-logo"' in html
    assert "metric-card-primary" in html
    assert 'class="branch-table"' in html
    assert "#0f4c81" in html
    assert "Čas počátku" not in html
    assert "Čas konce" not in html
    assert "break-before: page" in html
    assert "page-break-before: always" in html


def test_monthly_plynomery_billing_report_html_omits_control_meter_branch_share():
    branch = BranchBillingSummary(
        key="INNOGY_L",
        title="INNOGY L",
        billing_ident="INNOGY_L",
        billing_start_value=180.0,
        billing_end_value=200.0,
        billing_consumption=20.0,
        billing_start_reading_at=datetime.datetime(2026, 7, 1),
        billing_end_reading_at=datetime.datetime(2026, 8, 1),
        submeter_consumption_total=16.0,
        difference_vs_submeters=4.0,
        submeter_coverage_percent=80.0,
        direct_submeter_count=4,
        missing_direct_submeter_count=0,
        residual_label=None,
        residual_consumption=None,
        device_rows=(
            BranchDeviceConsumption(
                identifikace="L2-L3_P8",
                parent_identifikace=None,
                level=0,
                included_in_branch_sum=True,
                start_value=100.0,
                end_value=110.0,
                consumption=10.0,
                start_measured_at=datetime.datetime(2026, 7, 1),
                end_measured_at=datetime.datetime(2026, 8, 1),
                branch_share_percent=50.0,
                child_submeter_consumption_total=11.0,
                child_submeter_difference=-1.0,
                child_submeter_count=6,
                missing_child_submeter_count=0,
            ),
            BranchDeviceConsumption(
                identifikace="L2-L3_P1",
                parent_identifikace="L2-L3_P8",
                level=1,
                included_in_branch_sum=False,
                start_value=5.0,
                end_value=12.0,
                consumption=7.0,
                start_measured_at=datetime.datetime(2026, 7, 1),
                end_measured_at=datetime.datetime(2026, 8, 1),
                branch_share_percent=35.0,
            ),
        ),
    )
    report = MonthlyBillingReportData(
        generated_at=datetime.datetime(2026, 8, 2, 9, 0),
        period_start=datetime.datetime(2026, 7, 1),
        period_end=datetime.datetime(2026, 8, 1),
        year=2026,
        month=7,
        branches=(branch,),
    )

    html = build_monthly_plynomery_billing_report_html(report)

    assert "% podíl na větvi" in html
    assert "35.0 %" in html
    assert "50.0 %" not in html
    assert "kontrolní meziměřidlo pro 6 koncových" in html
    assert "(součet podružných: 11.000 m³; rozdíl: -1.000 m³)" in html
    assert "control-meter-row" in html
