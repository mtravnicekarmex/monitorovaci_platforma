from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import math
from zoneinfo import ZoneInfo

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.db.connect import ENGINE_PG, get_session_pg
from moduly.mereni.plynomery.branches import (
    PLYNOMERY_BRANCH_CONFIGS,
    PlynomeryBranchConfig,
    PlynomeryMeterNode,
)
from moduly.mereni.plynomery.database.models import (
    PlynomeryFakturacniOdecet,
)
from moduly.mereni.plynomery.database.plynomery_db_vse import (
    ensure_billing_readings_table,
)


PRAGUE_TZ = ZoneInfo("Europe/Prague")


class PlynomeryBillingError(RuntimeError):
    """Raised when plynomery billing readings or report data are invalid."""


@dataclass(frozen=True)
class BillingReadingInput:
    identifikace: str
    period_start: datetime
    period_end: datetime
    reading_at: datetime
    objem: float
    entered_by: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class BillingReadingRecord:
    id: int
    identifikace: str
    period_start: datetime
    period_end: datetime
    reading_at: datetime
    objem: float
    source: str
    entered_by: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MeterSnapshot:
    identifikace: str
    objem: float
    measured_at: datetime | None


@dataclass(frozen=True)
class BranchDeviceConsumption:
    identifikace: str
    parent_identifikace: str | None
    level: int
    included_in_branch_sum: bool
    start_value: float | None
    end_value: float | None
    consumption: float | None
    start_measured_at: datetime | None
    end_measured_at: datetime | None
    branch_share_percent: float | None = None
    child_submeter_consumption_total: float | None = None
    child_submeter_difference: float | None = None
    child_submeter_count: int = 0
    missing_child_submeter_count: int = 0


@dataclass(frozen=True)
class BranchBillingSummary:
    key: str
    title: str
    billing_ident: str
    billing_start_value: float | None
    billing_end_value: float | None
    billing_consumption: float | None
    billing_start_reading_at: datetime | None
    billing_end_reading_at: datetime | None
    submeter_consumption_total: float | None
    difference_vs_submeters: float | None
    submeter_coverage_percent: float | None
    direct_submeter_count: int
    missing_direct_submeter_count: int
    residual_label: str | None
    residual_consumption: float | None
    device_rows: tuple[BranchDeviceConsumption, ...]


@dataclass(frozen=True)
class MonthlyBillingReportData:
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    year: int
    month: int
    branches: tuple[BranchBillingSummary, ...]

    @property
    def month_label(self) -> str:
        return f"{self.month:02d}/{self.year}"

    @property
    def date_range_label(self) -> str:
        period_end_inclusive = self.period_end - timedelta(days=1)
        return f"{self.period_start:%d.%m.%Y} - {period_end_inclusive:%d.%m.%Y}"


@dataclass(frozen=True)
class BillingReportInputIssue:
    identifikace: str
    title: str
    issue_type: str
    message: str


def resolve_month_period(year: int, month: int) -> tuple[datetime, datetime]:
    if month < 1 or month > 12:
        raise ValueError("month must be in range 1..12")
    period_start = datetime(year, month, 1)
    if month == 12:
        period_end = datetime(year + 1, 1, 1)
    else:
        period_end = datetime(year, month + 1, 1)
    return period_start, period_end


def resolve_month_period_from_date(target_date: date) -> tuple[datetime, datetime]:
    return resolve_month_period(target_date.year, target_date.month)


def _normalize_datetime(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise PlynomeryBillingError(f"{field_name} musi byt datum a cas.")
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(PRAGUE_TZ).replace(tzinfo=None)


def _normalize_reading_input(reading: BillingReadingInput) -> dict[str, object]:
    identifikace = str(reading.identifikace or "").strip()
    if not identifikace:
        raise PlynomeryBillingError("Identifikace fakturačního plynoměru nesmí být prázdná.")
    allowed_billing_idents = {config.billing_ident for config in PLYNOMERY_BRANCH_CONFIGS}
    if identifikace not in allowed_billing_idents:
        raise PlynomeryBillingError(f"Neznámý fakturační plynoměr: {identifikace}.")
    period_start = _normalize_datetime(reading.period_start, field_name="Zacatek obdobi")
    period_end = _normalize_datetime(reading.period_end, field_name="Konec obdobi")
    reading_at = _normalize_datetime(reading.reading_at, field_name="Cas odectu")
    if period_end <= period_start:
        raise PlynomeryBillingError("Konec období musí být po začátku období.")
    objem = float(reading.objem)
    if not math.isfinite(objem):
        raise PlynomeryBillingError("Stav fakturačního plynoměru musí být konečné číslo.")
    if objem < 0:
        raise PlynomeryBillingError("Stav fakturačního plynoměru nesmí být záporný.")
    return {
        "identifikace": identifikace,
        "period_start": period_start,
        "period_end": period_end,
        "reading_at": reading_at,
        "objem": objem,
        "source": "manual",
        "entered_by": (str(reading.entered_by).strip() or None)
        if reading.entered_by is not None
        else None,
        "note": (str(reading.note).strip() or None)
        if reading.note is not None
        else None,
    }


def upsert_billing_readings(readings: tuple[BillingReadingInput, ...]) -> int:
    if not readings:
        return 0
    ensure_billing_readings_table()
    normalized_rows = [_normalize_reading_input(reading) for reading in readings]
    insert_stmt = insert(PlynomeryFakturacniOdecet).values(normalized_rows)
    with Session(ENGINE_PG) as session:
        result = session.execute(insert_stmt)
        session.commit()
        return int(result.rowcount or 0)


def _record_from_model(row: PlynomeryFakturacniOdecet) -> BillingReadingRecord:
    return BillingReadingRecord(
        id=int(row.id),
        identifikace=str(row.identifikace),
        period_start=row.period_start,
        period_end=row.period_end,
        reading_at=row.reading_at,
        objem=float(row.objem),
        source=str(row.source),
        entered_by=row.entered_by,
        note=row.note,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _latest_billing_rows_by_identifikace(
    rows: tuple[PlynomeryFakturacniOdecet, ...] | list[PlynomeryFakturacniOdecet],
) -> tuple[PlynomeryFakturacniOdecet, ...]:
    latest_rows: dict[str, PlynomeryFakturacniOdecet] = {}
    for row in rows:
        identifikace = str(row.identifikace)
        current = latest_rows.get(identifikace)
        if current is None or (
            row.reading_at,
            row.created_at,
            row.id,
        ) > (
            current.reading_at,
            current.created_at,
            current.id,
        ):
            latest_rows[identifikace] = row
    return tuple(latest_rows[identifikace] for identifikace in sorted(latest_rows))


def list_billing_readings_for_period(
    period_start: datetime,
    period_end: datetime,
) -> tuple[BillingReadingRecord, ...]:
    ensure_billing_readings_table()
    allowed_billing_idents = tuple(
        config.billing_ident for config in PLYNOMERY_BRANCH_CONFIGS
    )
    session = get_session_pg()
    try:
        rows = (
            session.query(PlynomeryFakturacniOdecet)
            .filter(
                PlynomeryFakturacniOdecet.identifikace.in_(allowed_billing_idents),
                PlynomeryFakturacniOdecet.period_start == period_start,
                PlynomeryFakturacniOdecet.period_end == period_end,
            )
            .order_by(
                PlynomeryFakturacniOdecet.identifikace.asc(),
                PlynomeryFakturacniOdecet.reading_at.desc(),
                PlynomeryFakturacniOdecet.created_at.desc(),
                PlynomeryFakturacniOdecet.id.desc(),
            )
            .all()
        )
        return tuple(
            _record_from_model(row)
            for row in _latest_billing_rows_by_identifikace(rows)
        )
    finally:
        session.close()


def load_latest_previous_billing_readings(
    period_start: datetime,
) -> dict[str, BillingReadingRecord]:
    ensure_billing_readings_table()
    previous_cutoff_exclusive = period_start + timedelta(days=1)
    result: dict[str, BillingReadingRecord] = {}
    session = get_session_pg()
    try:
        for config in PLYNOMERY_BRANCH_CONFIGS:
            row = (
                session.query(PlynomeryFakturacniOdecet)
                .filter(
                    PlynomeryFakturacniOdecet.identifikace == config.billing_ident,
                    PlynomeryFakturacniOdecet.reading_at < previous_cutoff_exclusive,
                )
                .order_by(
                    PlynomeryFakturacniOdecet.reading_at.desc(),
                    PlynomeryFakturacniOdecet.created_at.desc(),
                    PlynomeryFakturacniOdecet.id.desc(),
                )
                .first()
            )
            if row is not None:
                result[config.billing_ident] = _record_from_model(row)
        return result
    finally:
        session.close()


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=PRAGUE_TZ)
    return value.astimezone(UTC)


def _normalize_snapshot_time(time_utc: object, local_time: object) -> datetime | None:
    if isinstance(time_utc, datetime):
        if time_utc.tzinfo is None or time_utc.utcoffset() is None:
            return time_utc.replace(tzinfo=UTC).astimezone(PRAGUE_TZ).replace(tzinfo=None)
        return time_utc.astimezone(PRAGUE_TZ).replace(tzinfo=None)
    if isinstance(local_time, datetime):
        return local_time
    return None


def load_last_valid_measurements_at_or_before(
    identifiers: tuple[str, ...],
    cutoff: datetime,
) -> dict[str, MeterSnapshot]:
    unique_identifiers = tuple(dict.fromkeys(str(identifier).strip() for identifier in identifiers if str(identifier).strip()))
    if not unique_identifiers:
        return {}

    statement = text(
        """
        WITH ranked_measurements AS (
            SELECT
                identifikace,
                objem,
                date,
                time_utc,
                ROW_NUMBER() OVER (
                    PARTITION BY identifikace
                    ORDER BY time_utc DESC NULLS LAST, date DESC NULLS LAST, id DESC
                ) AS row_num
            FROM monitoring."Mereni_plynomery_vse"
            WHERE identifikace IN :identifiers
              AND objem IS NOT NULL
              AND platne = TRUE
              AND (
                    time_utc <= :cutoff_utc
                    OR (time_utc IS NULL AND date <= :cutoff_local)
                  )
        )
        SELECT identifikace, objem, date, time_utc
        FROM ranked_measurements
        WHERE row_num = 1
        """
    ).bindparams(bindparam("identifiers", expanding=True))

    with ENGINE_PG.connect() as conn:
        rows = conn.execute(
            statement,
            {
                "identifiers": unique_identifiers,
                "cutoff_utc": _to_utc(cutoff),
                "cutoff_local": cutoff,
            },
        ).all()

    return {
        str(row.identifikace): MeterSnapshot(
            identifikace=str(row.identifikace),
            objem=round(float(row.objem), 3),
            measured_at=_normalize_snapshot_time(row.time_utc, row.date),
        )
        for row in rows
    }


def _compute_consumption(start_value: float | None, end_value: float | None) -> float | None:
    if start_value is None or end_value is None:
        return None
    consumption = float(end_value) - float(start_value)
    if consumption < -0.0005:
        return None
    if abs(consumption) < 0.0005:
        consumption = 0.0
    return round(consumption, 3)


def _compute_difference(left_value: float | None, right_value: float | None) -> float | None:
    if left_value is None or right_value is None:
        return None
    difference = float(left_value) - float(right_value)
    if abs(difference) < 0.0005:
        difference = 0.0
    return round(difference, 3)


def _safe_ratio_percent(value: float | None, total: float | None) -> float | None:
    if value is None or total is None:
        return None
    numeric_total = float(total)
    if numeric_total <= 0:
        return None
    return round(float(value) / numeric_total * 100, 1)


def validate_monthly_billing_report_inputs(
    *,
    current_readings: dict[str, BillingReadingRecord],
    previous_readings: dict[str, BillingReadingRecord],
) -> tuple[BillingReportInputIssue, ...]:
    issues: list[BillingReportInputIssue] = []
    for config in PLYNOMERY_BRANCH_CONFIGS:
        current = current_readings.get(config.billing_ident)
        previous = previous_readings.get(config.billing_ident)
        if current is None:
            issues.append(
                BillingReportInputIssue(
                    identifikace=config.billing_ident,
                    title=config.title,
                    issue_type="missing_current",
                    message="Chybí aktuální fakturační stav pro zvolené období.",
                )
            )
            continue
        if previous is None:
            issues.append(
                BillingReportInputIssue(
                    identifikace=config.billing_ident,
                    title=config.title,
                    issue_type="missing_previous",
                    message="Chybí předchozí fakturační stav pro výpočet spotřeby.",
                )
            )
            continue
        if current.reading_at <= previous.reading_at:
            issues.append(
                BillingReportInputIssue(
                    identifikace=config.billing_ident,
                    title=config.title,
                    issue_type="reading_time_not_after_previous",
                    message="Aktuální čas odečtu musí být po předchozím odečtu.",
                )
            )
            continue
        if _compute_consumption(previous.objem, current.objem) is None:
            issues.append(
                BillingReportInputIssue(
                    identifikace=config.billing_ident,
                    title=config.title,
                    issue_type="reading_decreased",
                    message="Aktuální stav je nižší než předchozí fakturační stav.",
                )
            )
    return tuple(issues)


def _iter_meter_nodes(
    nodes: tuple[PlynomeryMeterNode, ...],
    *,
    parent_identifikace: str | None = None,
    level: int = 0,
) -> tuple[tuple[PlynomeryMeterNode, str | None, int], ...]:
    result: list[tuple[PlynomeryMeterNode, str | None, int]] = []
    for node in nodes:
        result.append((node, parent_identifikace, level))
        result.extend(
            _iter_meter_nodes(
                node.children,
                parent_identifikace=node.identifikace,
                level=level + 1,
            )
        )
    return tuple(result)


def _build_device_rows(
    config: PlynomeryBranchConfig,
    *,
    start_snapshots: dict[str, MeterSnapshot],
    end_snapshots: dict[str, MeterSnapshot],
    branch_consumption: float | None,
) -> tuple[BranchDeviceConsumption, ...]:
    direct_identifiers = set(config.direct_submeter_idents)

    def build_node_rows(
        node: PlynomeryMeterNode,
        *,
        parent_identifikace: str | None,
        level: int,
    ) -> tuple[list[BranchDeviceConsumption], list[float], int, int]:
        start_snapshot = start_snapshots.get(node.identifikace)
        end_snapshot = end_snapshots.get(node.identifikace)
        consumption = _compute_consumption(
            None if start_snapshot is None else start_snapshot.objem,
            None if end_snapshot is None else end_snapshot.objem,
        )
        child_rows: list[BranchDeviceConsumption] = []
        child_terminal_consumptions: list[float] = []
        child_terminal_count = 0
        missing_child_terminal_count = 0
        for child in node.children:
            (
                built_child_rows,
                terminal_consumptions,
                terminal_count,
                missing_terminal_count,
            ) = build_node_rows(
                child,
                parent_identifikace=node.identifikace,
                level=level + 1,
            )
            child_rows.extend(built_child_rows)
            child_terminal_consumptions.extend(terminal_consumptions)
            child_terminal_count += terminal_count
            missing_child_terminal_count += missing_terminal_count

        child_submeter_total = None
        child_submeter_difference = None
        if node.children and missing_child_terminal_count == 0:
            child_submeter_total = round(sum(child_terminal_consumptions), 3)
            child_submeter_difference = _compute_difference(
                consumption,
                child_submeter_total,
            )

        row = BranchDeviceConsumption(
            identifikace=node.identifikace,
            parent_identifikace=parent_identifikace,
            level=level,
            included_in_branch_sum=node.identifikace in direct_identifiers,
            start_value=None if start_snapshot is None else start_snapshot.objem,
            end_value=None if end_snapshot is None else end_snapshot.objem,
            consumption=consumption,
            start_measured_at=None if start_snapshot is None else start_snapshot.measured_at,
            end_measured_at=None if end_snapshot is None else end_snapshot.measured_at,
            branch_share_percent=_safe_ratio_percent(consumption, branch_consumption),
            child_submeter_consumption_total=child_submeter_total,
            child_submeter_difference=child_submeter_difference,
            child_submeter_count=child_terminal_count,
            missing_child_submeter_count=missing_child_terminal_count,
        )
        if node.children:
            return (
                [row, *child_rows],
                child_terminal_consumptions,
                child_terminal_count,
                missing_child_terminal_count,
            )
        if consumption is None:
            return ([row], [], 1, 1)
        return ([row], [consumption], 1, 0)

    rows: list[BranchDeviceConsumption] = []
    for node in config.submeters:
        built_rows, _, _, _ = build_node_rows(
            node,
            parent_identifikace=None,
            level=0,
        )
        rows.extend(built_rows)
    return tuple(rows)


def _build_branch_summary(
    config: PlynomeryBranchConfig,
    *,
    current_readings: dict[str, BillingReadingRecord],
    previous_readings: dict[str, BillingReadingRecord],
    period_start: datetime,
    period_end: datetime,
    start_snapshots: dict[str, MeterSnapshot],
    end_snapshots: dict[str, MeterSnapshot],
) -> BranchBillingSummary:
    current_reading = current_readings.get(config.billing_ident)
    previous_reading = previous_readings.get(config.billing_ident)
    billing_start_value = None if previous_reading is None else previous_reading.objem
    billing_end_value = None if current_reading is None else current_reading.objem
    billing_consumption = _compute_consumption(billing_start_value, billing_end_value)

    device_rows = _build_device_rows(
        config,
        start_snapshots=start_snapshots,
        end_snapshots=end_snapshots,
        branch_consumption=billing_consumption,
    )
    direct_rows = tuple(row for row in device_rows if row.included_in_branch_sum)
    missing_direct_count = sum(1 for row in direct_rows if row.consumption is None)
    if not direct_rows:
        submeter_total = None
    else:
        submeter_total = round(sum(float(row.consumption or 0.0) for row in direct_rows), 3)

    difference = None
    coverage_percent = None
    if direct_rows and billing_consumption is not None and submeter_total is not None and missing_direct_count == 0:
        difference = round(billing_consumption - submeter_total, 3)
        if billing_consumption > 0:
            coverage_percent = round(submeter_total / billing_consumption * 100, 1)

    return BranchBillingSummary(
        key=config.key,
        title=config.title,
        billing_ident=config.billing_ident,
        billing_start_value=billing_start_value,
        billing_end_value=billing_end_value,
        billing_consumption=billing_consumption,
        billing_start_reading_at=None if previous_reading is None else previous_reading.reading_at,
        billing_end_reading_at=None if current_reading is None else current_reading.reading_at,
        submeter_consumption_total=submeter_total,
        difference_vs_submeters=difference,
        submeter_coverage_percent=coverage_percent,
        direct_submeter_count=len(direct_rows),
        missing_direct_submeter_count=missing_direct_count,
        residual_label=config.residual_label,
        residual_consumption=difference if config.residual_label and difference is not None else None,
        device_rows=device_rows,
    )


def _load_branch_submeter_snapshots(
    config: PlynomeryBranchConfig,
    *,
    current_readings: dict[str, BillingReadingRecord],
    previous_readings: dict[str, BillingReadingRecord],
    period_start: datetime,
    period_end: datetime,
) -> tuple[dict[str, MeterSnapshot], dict[str, MeterSnapshot]]:
    identifiers = config.all_submeter_idents
    if not identifiers:
        return {}, {}

    previous = previous_readings.get(config.billing_ident)
    current = current_readings.get(config.billing_ident)
    start_cutoff = previous.reading_at if previous is not None else period_start
    end_cutoff = current.reading_at if current is not None else period_end
    return (
        load_last_valid_measurements_at_or_before(identifiers, start_cutoff),
        load_last_valid_measurements_at_or_before(identifiers, end_cutoff),
    )


def build_monthly_billing_report_data(
    *,
    year: int,
    month: int,
) -> MonthlyBillingReportData:
    period_start, period_end = resolve_month_period(year, month)
    current_readings = {
        row.identifikace: row
        for row in list_billing_readings_for_period(period_start, period_end)
    }
    previous_readings = load_latest_previous_billing_readings(period_start)

    branches: list[BranchBillingSummary] = []
    for config in PLYNOMERY_BRANCH_CONFIGS:
        start_snapshots, end_snapshots = _load_branch_submeter_snapshots(
            config,
            current_readings=current_readings,
            previous_readings=previous_readings,
            period_start=period_start,
            period_end=period_end,
        )
        branches.append(
            _build_branch_summary(
                config,
                current_readings=current_readings,
                previous_readings=previous_readings,
                period_start=period_start,
                period_end=period_end,
                start_snapshots=start_snapshots,
                end_snapshots=end_snapshots,
            )
        )
    return MonthlyBillingReportData(
        generated_at=datetime.now(PRAGUE_TZ).replace(tzinfo=None),
        period_start=period_start,
        period_end=period_end,
        year=year,
        month=month,
        branches=tuple(branches),
    )
