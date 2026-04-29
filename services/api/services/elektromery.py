from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from core.db.connect import get_session_ms
from moduly.mereni.elektromery.TS.historie_TS import (
    INTERVALY_TS_1,
    INTERVALY_TS_2,
    INTERVALY_TS_3,
    ziskej_TS_1,
    ziskej_TS_2,
    ziskej_TS_3,
)
from moduly.mereni.elektromery.database.models import Elektromer_areal_Mereni


@dataclass(frozen=True)
class BranchDashboardConfig:
    key: str
    title: str
    intervals: tuple[tuple[datetime, datetime, list[str]], ...]
    membership_resolver: Callable[[datetime], list[str]]


BRANCH_DASHBOARD_CONFIGS: tuple[BranchDashboardConfig, ...] = (
    BranchDashboardConfig(
        key="TS1",
        title="TS1",
        intervals=tuple(INTERVALY_TS_1),
        membership_resolver=ziskej_TS_1,
    ),
    BranchDashboardConfig(
        key="TS2",
        title="TS2",
        intervals=tuple(INTERVALY_TS_2),
        membership_resolver=ziskej_TS_2,
    ),
    BranchDashboardConfig(
        key="TS3",
        title="TS3",
        intervals=tuple(INTERVALY_TS_3),
        membership_resolver=ziskej_TS_3,
    ),
)


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.to_pydatetime()
    if pd.isna(value):
        return None
    return value


def _serialize_dataframe_rows(df: pd.DataFrame) -> list[dict[str, object]]:
    if df.empty:
        return []
    return [
        {str(column): _serialize_value(value) for column, value in row.items()}
        for row in df.to_dict(orient="records")
    ]


def _resolve_branch_segments(
    config_item: BranchDashboardConfig,
    start_dt: datetime,
    end_dt: datetime,
    additional_boundaries: Iterable[datetime] = (),
    merge_adjacent: bool = True,
) -> list[tuple[datetime, datetime, tuple[str, ...]]]:
    boundaries = {start_dt, end_dt}
    one_second = timedelta(seconds=1)

    for interval_start, interval_end, _ in config_item.intervals:
        effective_start = max(start_dt, interval_start)
        effective_end = min(end_dt, interval_end + one_second)
        if effective_start < effective_end:
            boundaries.add(effective_start)
            boundaries.add(effective_end)

    for boundary in additional_boundaries:
        if start_dt < boundary < end_dt:
            boundaries.add(boundary)

    ordered_boundaries = sorted(boundaries)
    segments: list[tuple[datetime, datetime, tuple[str, ...]]] = []
    for segment_start, segment_end in zip(ordered_boundaries, ordered_boundaries[1:]):
        if segment_start >= segment_end:
            continue
        midpoint = segment_start + (segment_end - segment_start) / 2
        active_devices = tuple(dict.fromkeys(config_item.membership_resolver(midpoint)))
        if not active_devices:
            continue
        if merge_adjacent and segments and segments[-1][2] == active_devices and segments[-1][1] == segment_start:
            previous_start, _, previous_devices = segments[-1]
            segments[-1] = (previous_start, segment_end, previous_devices)
        else:
            segments.append((segment_start, segment_end, active_devices))
    return segments


def _load_measurement_rows(
    identifiers: tuple[str, ...],
    *,
    lookback_start: datetime,
    period_end: datetime,
) -> list[dict[str, object]]:
    if not identifiers:
        return []

    session = get_session_ms()
    try:
        rows = (
            session.query(
                Elektromer_areal_Mereni.date,
                Elektromer_areal_Mereni.identifikace,
                Elektromer_areal_Mereni.seriove_cislo,
                Elektromer_areal_Mereni.vt,
                Elektromer_areal_Mereni.nt,
                Elektromer_areal_Mereni.total,
            )
            .filter(
                Elektromer_areal_Mereni.identifikace.in_(identifiers),
                Elektromer_areal_Mereni.date >= lookback_start,
                Elektromer_areal_Mereni.date <= period_end,
            )
            .order_by(Elektromer_areal_Mereni.identifikace.asc(), Elektromer_areal_Mereni.date.asc())
            .all()
        )
        return [
            {
                "date": row.date,
                "identifikace": row.identifikace,
                "seriove_cislo": row.seriove_cislo,
                "vt": row.vt,
                "nt": row.nt,
                "total": row.total,
            }
            for row in rows
        ]
    finally:
        session.close()


def _empty_prepared_measurements() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "date",
            "identifikace",
            "seriove_cislo",
            "vt",
            "nt",
            "total",
            "stav_celkem",
        ]
    )


def _prepare_measurements(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return _empty_prepared_measurements()

    prepared = df.copy()
    for column in ("date", "identifikace", "seriove_cislo", "vt", "nt", "total"):
        if column not in prepared.columns:
            prepared[column] = pd.NA

    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared["identifikace"] = prepared["identifikace"].astype("string")
    prepared["seriove_cislo"] = prepared["seriove_cislo"].astype("string")
    for column in ("vt", "nt", "total"):
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    prepared = prepared.dropna(subset=["date", "identifikace"]).sort_values(
        ["identifikace", "date"],
        ascending=[True, True],
    )
    if prepared.empty:
        return _empty_prepared_measurements()

    prepared["stav_celkem"] = prepared["total"]
    missing_total = prepared["stav_celkem"].isna()
    prepared.loc[missing_total & prepared["vt"].notna() & prepared["nt"].notna(), "stav_celkem"] = (
        prepared["vt"] + prepared["nt"]
    )
    prepared.loc[prepared["stav_celkem"].isna(), "stav_celkem"] = prepared["vt"]
    prepared = prepared.dropna(subset=["stav_celkem"]).reset_index(drop=True)
    if prepared.empty:
        return _empty_prepared_measurements()
    return prepared


def _state_at_or_before(
    measurements_df: pd.DataFrame,
    identifier: str,
    cutoff: datetime,
    column: str,
) -> float | None:
    if measurements_df.empty or column not in measurements_df.columns:
        return None
    device_df = measurements_df.loc[
        (measurements_df["identifikace"].astype(str) == identifier)
        & (measurements_df["date"] <= cutoff)
    ].copy()
    if device_df.empty:
        return None
    device_df[column] = pd.to_numeric(device_df[column], errors="coerce")
    device_df = device_df.dropna(subset=["date", column]).sort_values("date")
    if device_df.empty:
        return None
    return round(float(device_df[column].iloc[-1]), 3)


def _compute_consumption(start_value: float | None, end_value: float | None) -> float | None:
    if start_value is None or end_value is None or end_value < start_value:
        return None
    return round(float(end_value) - float(start_value), 3)


def _iter_period_days(period_start: datetime, period_end: datetime) -> tuple[datetime, ...]:
    days: list[datetime] = []
    current = period_start
    while current < period_end:
        days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def load_branch_period_overview(
    *,
    period_start: datetime,
    period_end: datetime,
) -> list[dict[str, object]]:
    if period_start >= period_end:
        raise ValueError("period_start musi byt mensi nez period_end.")

    day_boundaries = tuple(
        period_start + timedelta(days=day_index)
        for day_index in range((period_end.date() - period_start.date()).days + 1)
    )
    lookback_start = period_start - timedelta(days=14)

    branch_payloads: list[dict[str, object]] = []
    for config_item in BRANCH_DASHBOARD_CONFIGS:
        effective_segments = _resolve_branch_segments(
            config_item,
            period_start,
            period_end,
            additional_boundaries=day_boundaries,
            merge_adjacent=False,
        )
        active_devices = tuple(
            dict.fromkeys(
                identifier
                for _, _, segment_identifiers in effective_segments
                for identifier in segment_identifiers
            )
        )

        measurement_rows = _load_measurement_rows(
            active_devices,
            lookback_start=lookback_start,
            period_end=period_end,
        )
        measurements_df = _prepare_measurements(pd.DataFrame(measurement_rows))
        period_measurements_df = measurements_df.loc[
            (measurements_df["date"] >= period_start) & (measurements_df["date"] <= period_end)
        ].copy()
        last_actual_timestamp = (
            None if period_measurements_df.empty else pd.to_datetime(period_measurements_df["date"]).max()
        )

        device_totals: dict[str, dict[str, object]] = {
            identifier: {
                "identifikace": identifier,
                "start_value": None,
                "end_value": None,
                "spotreba": 0.0,
                "spotreba_vt": 0.0,
                "spotreba_nt": 0.0,
                "active_days": 0,
            }
            for identifier in active_devices
        }
        daily_rows: list[dict[str, object]] = []

        for day_start in _iter_period_days(period_start, period_end):
            day_end = day_start + timedelta(days=1)
            midpoint = day_start + timedelta(hours=12)
            active_day_devices = tuple(dict.fromkeys(config_item.membership_resolver(midpoint)))
            actual_total = 0.0
            vt_total = 0.0
            nt_total = 0.0
            device_values: dict[str, float] = {}

            for identifier in active_day_devices:
                device_stats = device_totals.setdefault(
                    identifier,
                    {
                        "identifikace": identifier,
                        "start_value": None,
                        "end_value": None,
                        "spotreba": 0.0,
                        "spotreba_vt": 0.0,
                        "spotreba_nt": 0.0,
                        "active_days": 0,
                    },
                )
                start_value = _state_at_or_before(measurements_df, identifier, day_start, "stav_celkem")
                end_value = _state_at_or_before(measurements_df, identifier, day_end, "stav_celkem")
                consumption = _compute_consumption(start_value, end_value)
                vt_consumption = _compute_consumption(
                    _state_at_or_before(measurements_df, identifier, day_start, "vt"),
                    _state_at_or_before(measurements_df, identifier, day_end, "vt"),
                )
                nt_consumption = _compute_consumption(
                    _state_at_or_before(measurements_df, identifier, day_start, "nt"),
                    _state_at_or_before(measurements_df, identifier, day_end, "nt"),
                )

                if start_value is not None and device_stats["start_value"] is None:
                    device_stats["start_value"] = start_value
                if end_value is not None:
                    device_stats["end_value"] = end_value
                device_stats["active_days"] = int(device_stats["active_days"]) + 1

                actual_value = round(float(consumption or 0.0), 3)
                vt_value = round(float(vt_consumption or 0.0), 3)
                nt_value = round(float(nt_consumption or 0.0), 3)
                device_stats["spotreba"] = round(float(device_stats["spotreba"]) + actual_value, 3)
                device_stats["spotreba_vt"] = round(float(device_stats["spotreba_vt"]) + vt_value, 3)
                device_stats["spotreba_nt"] = round(float(device_stats["spotreba_nt"]) + nt_value, 3)

                actual_total = round(actual_total + actual_value, 3)
                vt_total = round(vt_total + vt_value, 3)
                nt_total = round(nt_total + nt_value, 3)
                device_values[identifier] = actual_value

            daily_rows.append(
                {
                    "date": day_start,
                    "actual_total": actual_total,
                    "vt_total": vt_total,
                    "nt_total": nt_total,
                    "device_values": device_values,
                }
            )

        actual_total = round(sum(float(row["actual_total"]) for row in daily_rows), 3)
        vt_total = round(sum(float(row["vt_total"]) for row in daily_rows), 3)
        nt_total = round(sum(float(row["nt_total"]) for row in daily_rows), 3)
        device_rows = list(device_totals.values())
        for row in device_rows:
            row["podil_procent"] = round(float(row["spotreba"]) / actual_total * 100, 1) if actual_total > 0 else 0.0
        device_rows.sort(key=lambda row: (-float(row["spotreba"]), str(row["identifikace"])))

        branch_payloads.append(
            {
                "key": config_item.key,
                "title": config_item.title,
                "active_devices": list(active_devices),
                "period_start": period_start,
                "period_end": period_end,
                "last_actual_timestamp": last_actual_timestamp.to_pydatetime() if last_actual_timestamp is not None else None,
                "actual_total": actual_total,
                "vt_total": vt_total,
                "nt_total": nt_total,
                "device_consumption_rows": _serialize_dataframe_rows(pd.DataFrame(device_rows)),
                "daily_rows": daily_rows,
            }
        )

    return branch_payloads
