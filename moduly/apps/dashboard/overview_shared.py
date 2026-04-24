from __future__ import annotations

import datetime
from pathlib import Path
import sys

import streamlit as st
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.time_utils import prague_now_naive
from core.db.connect import get_session_ms, get_session_pg
from moduly.apps.dashboard.api_client import DashboardApiError
from moduly.apps.dashboard.elektromery_shared import (
    load_ident_options as load_elektromery_ident_options,
)
from moduly.apps.dashboard.kalorimetry_shared import (
    load_ident_options as load_kalorimetry_ident_options,
)
from moduly.apps.dashboard.manometry_shared import (
    load_device_detail as load_manometry_device_detail,
    convert_pressure_value_to_bar,
    load_ident_options as load_manometry_ident_options,
)
from moduly.apps.dashboard.navigation_config import SECTIONS, get_section_definition
from moduly.apps.dashboard.plynomery_shared import (
    load_ident_options as load_plynomery_ident_options,
)
from moduly.apps.dashboard.vodomery_shared import (
    load_all_open_events as load_vodomery_open_events,
    load_branch_day_overview as load_vodomery_branch_day_overview,
    load_ident_options as load_vodomery_ident_options,
    load_overview_metrics as load_vodomery_overview_metrics,
)
from moduly.mereni.elektromery.database.models import Elektromer_areal_Mereni
from moduly.mereni.kalorimetry.database.models import Kalorimetr_areal_Mereni
from moduly.mereni.manometry.database.models import Mereni_manometry
from moduly.mereni.plynomery.database.models import Plynomer_areal_Mereni
from moduly.mereni.vodomery.database.models import Mereni_vodomery


RECENT_WINDOW_DAYS = 7
MANOMETRY_CHART_DEVICE_LIMIT = 3
MANOMETRY_CHART_LOOKBACK_HOURS = 24
MODULE_OVERVIEW_PAGE_KEYS = {
    "vodomery": "vodomery_overview",
    "manometry": "manometry_overview",
    "plynomery": "plynomery_overview",
    "elektromery": "elektromery_overview",
    "kalorimetry": "kalorimetry_overview",
}
MODULE_ACCENT_COLORS = {
    "vodomery": "#0f766e",
    "manometry": "#2563eb",
    "plynomery": "#d97706",
    "elektromery": "#dc2626",
    "kalorimetry": "#ea580c",
}
VODOMERY_ALARM_EVENT_LIMIT = 6
VODOMERY_ALARM_ZERO_FLOW_MIN_DURATION_MINUTES = 60 * 60
VODOMERY_ALARM_EVENT_TYPE_LABELS = {
    "NIGHT_USAGE": "Noční odběr",
    "SPIKE": "Špička",
    "LONG_LEAK": "Dlouhý únik",
    "ZERO_FLOW": "Bez průtoku",
    "EXPECTED_ZERO_USAGE": "Odběr v expected zero",
    "OUTLIER_REVIEW": "Outlier review",
}
VODOMERY_ALARM_SEVERITY_LABELS = {
    "CRITICAL": "Critical",
    "HIGH": "High",
    "MEDIUM": "Medium",
    "LOW": "Low",
}
VODOMERY_ALARM_SEVERITY_ORDER = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
}


def format_overview_timestamp(value: object) -> str:
    if value is None:
        return "Bez dat"
    if isinstance(value, datetime.datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, datetime.date):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return "Bez dat"
        try:
            parsed = datetime.datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            return normalized
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed.strftime("%d.%m.%Y %H:%M")
    return str(value)


def summarize_dashboard_overview(cards: list[dict[str, object]]) -> dict[str, int]:
    accessible_cards = [card for card in cards if bool(card.get("accessible"))]
    return {
        "accessible_modules": len(accessible_cards),
        "modules_with_recent_data": sum(1 for card in accessible_cards if int(card.get("recent_measurements") or 0) > 0),
        "total_devices": sum(int(card.get("total_devices") or 0) for card in accessible_cards),
        "recent_measurements": sum(int(card.get("recent_measurements") or 0) for card in accessible_cards),
    }


def _build_empty_card(
    section_key: str,
    *,
    accessible: bool,
    description: str,
    error: str | None = None,
    title: str | None = None,
    icon: str | None = None,
    accent_color: str | None = None,
    page_key: str | None = None,
) -> dict[str, object]:
    section = get_section_definition(section_key)
    return {
        "section_key": section_key,
        "page_key": page_key if page_key is not None else MODULE_OVERVIEW_PAGE_KEYS.get(section_key),
        "title": title if title is not None else (section.label if section is not None else section_key),
        "icon": icon if icon is not None else (section.icon if section is not None else ""),
        "accent_color": accent_color if accent_color is not None else MODULE_ACCENT_COLORS.get(section_key, "#64748b"),
        "accessible": accessible,
        "total_devices": 0,
        "recent_devices": 0,
        "recent_measurements": 0,
        "last_measurement_at": None,
        "badges": [],
        "description": description,
        "error": error,
    }


def _apply_device_scope(query, ident_column, allowed_devices: tuple[str, ...], user_is_admin: bool):
    if user_is_admin:
        return query
    return query.filter(ident_column.in_(allowed_devices))


def _load_ms_measurement_metrics(
    *,
    measurement_model,
    ident_column,
    date_column,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
    valid_column=None,
) -> dict[str, object]:
    now = prague_now_naive()
    recent_cutoff = now - datetime.timedelta(days=RECENT_WINDOW_DAYS)

    session = get_session_ms()
    try:
        total_devices_query = session.query(func.count(func.distinct(ident_column))).filter(ident_column.is_not(None))
        recent_devices_query = session.query(func.count(func.distinct(ident_column))).filter(
            ident_column.is_not(None),
            date_column.is_not(None),
            date_column >= recent_cutoff,
            date_column <= now,
        )
        last_measurement_query = session.query(func.max(date_column)).filter(
            ident_column.is_not(None),
            date_column.is_not(None),
        )
        recent_measurements_query = session.query(measurement_model).filter(
            ident_column.is_not(None),
            date_column.is_not(None),
            date_column >= recent_cutoff,
            date_column <= now,
        )

        total_devices_query = _apply_device_scope(total_devices_query, ident_column, allowed_devices, user_is_admin)
        recent_devices_query = _apply_device_scope(recent_devices_query, ident_column, allowed_devices, user_is_admin)
        last_measurement_query = _apply_device_scope(last_measurement_query, ident_column, allowed_devices, user_is_admin)
        recent_measurements_query = _apply_device_scope(
            recent_measurements_query,
            ident_column,
            allowed_devices,
            user_is_admin,
        )

        recent_measurements = int(recent_measurements_query.count())
        metrics = {
            "total_devices": int(total_devices_query.scalar() or 0),
            "recent_devices": int(recent_devices_query.scalar() or 0),
            "recent_measurements": recent_measurements,
            "last_measurement_at": last_measurement_query.scalar(),
            "badges": [],
        }

        if valid_column is not None:
            valid_recent_measurements = int(recent_measurements_query.filter(valid_column == True).count())
            invalid_recent_measurements = max(recent_measurements - valid_recent_measurements, 0)
            metrics["badges"] = [
                {"label": "Platná měření", "value": f"{valid_recent_measurements:,}".replace(",", " ")},
                {"label": "Neplatná měření", "value": f"{invalid_recent_measurements:,}".replace(",", " ")},
            ]

        return metrics
    finally:
        session.close()


def _load_vodomery_card(allowed_devices: tuple[str, ...], user_is_admin: bool) -> dict[str, object]:
    end_date = prague_now_naive().date()
    start_date = end_date - datetime.timedelta(days=RECENT_WINDOW_DAYS - 1)
    metrics = load_vodomery_overview_metrics("VSE", start_date, end_date, allowed_devices, user_is_admin)
    total_devices = len(load_vodomery_ident_options("VSE", allowed_devices, user_is_admin))
    branch_rows = load_vodomery_branch_day_overview(end_date, allowed_devices, user_is_admin)

    session = get_session_pg()
    try:
        last_measurement_query = session.query(func.max(Mereni_vodomery.date)).filter(
            Mereni_vodomery.identifikace.is_not(None),
            Mereni_vodomery.date.is_not(None),
        )
        last_measurement_query = _apply_device_scope(
            last_measurement_query,
            Mereni_vodomery.identifikace,
            allowed_devices,
            user_is_admin,
        )
        last_measurement_at = last_measurement_query.scalar()
    finally:
        session.close()

    card = _build_empty_card(
        "vodomery",
        accessible=True,
        description="Souhrn za všechna dostupná vodoměrná měření, anomálie a eventy.",
    )
    card.update(
        {
            "total_devices": total_devices,
            "recent_devices": int(metrics.get("zarizeni", 0)),
            "recent_measurements": int(metrics.get("mereni", 0)),
            "last_measurement_at": last_measurement_at,
            "branch_chart_rows": branch_rows,
            "badges": [
                {"label": "Anomálie", "value": f"{int(metrics.get('anomalie', 0)):,}".replace(",", " ")},
                {"label": "Aktivní eventy", "value": f"{int(metrics.get('aktivni_eventy', 0)):,}".replace(",", " ")},
            ],
        }
    )
    return card


def _coerce_alarm_duration_minutes(value: object) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _is_visible_vodomery_alarm_event(event_type: str, duration_minutes: int) -> bool:
    if event_type == "ZERO_FLOW" and duration_minutes <= VODOMERY_ALARM_ZERO_FLOW_MIN_DURATION_MINUTES:
        return False
    return True


def build_vodomery_alarm_payload(open_events_df, *, limit: int = VODOMERY_ALARM_EVENT_LIMIT) -> dict[str, object]:
    if open_events_df is None or open_events_df.empty:
        return {
            "total_open_events": 0,
            "affected_devices": 0,
            "critical_count": 0,
            "high_count": 0,
            "medium_count": 0,
            "hidden_event_count": 0,
            "open_event_rows": [],
        }

    normalized_rows: list[dict[str, object]] = []
    for index, row in enumerate(open_events_df.to_dict("records")):
        event_type = str(row.get("event_type") or "")
        duration_minutes = _coerce_alarm_duration_minutes(row.get("duration_minutes"))
        if not _is_visible_vodomery_alarm_event(event_type, duration_minutes):
            continue
        severity = str(row.get("severity") or "").upper() or "UNKNOWN"
        normalized_rows.append(
            {
                "identifikace": str(row.get("identifikace") or "Neznámý vodoměr"),
                "event_type": event_type,
                "event_type_label": VODOMERY_ALARM_EVENT_TYPE_LABELS.get(event_type, event_type or "Neznámý event"),
                "start_time": row.get("start_time"),
                "end_time": row.get("end_time"),
                "duration_minutes": duration_minutes,
                "max_z_score": row.get("max_z_score"),
                "avg_z_score": row.get("avg_z_score"),
                "severity": severity,
                "severity_label": VODOMERY_ALARM_SEVERITY_LABELS.get(severity, severity or "Unknown"),
                "_source_order": index,
            }
        )

    normalized_rows.sort(
        key=lambda item: (
            VODOMERY_ALARM_SEVERITY_ORDER.get(str(item.get("severity") or "").upper(), 99),
            -int(item.get("duration_minutes") or 0),
            int(item.get("_source_order") or 0),
        )
    )

    visible_rows = []
    for row in normalized_rows[:max(limit, 0)]:
        visible_rows.append({key: value for key, value in row.items() if key != "_source_order"})

    return {
        "total_open_events": len(normalized_rows),
        "affected_devices": len({str(row["identifikace"]) for row in normalized_rows if row.get("identifikace")}),
        "critical_count": sum(1 for row in normalized_rows if row.get("severity") == "CRITICAL"),
        "high_count": sum(1 for row in normalized_rows if row.get("severity") == "HIGH"),
        "medium_count": sum(1 for row in normalized_rows if row.get("severity") == "MEDIUM"),
        "hidden_event_count": max(len(normalized_rows) - len(visible_rows), 0),
        "open_event_rows": visible_rows,
    }


def _load_vodomery_alarm_card(allowed_devices: tuple[str, ...], user_is_admin: bool) -> dict[str, object]:
    open_events_df = load_vodomery_open_events(allowed_devices, user_is_admin, limit=500)
    payload = build_vodomery_alarm_payload(open_events_df)

    card = _build_empty_card(
        "vodomery_alarm",
        accessible=True,
        description="Otevřené Anomaly eventy na vodoměrech.",
        title="Vodoměry alarm",
        icon="🚨",
        accent_color="#dc2626",
        page_key="vodomery_anomalie_eventy",
    )
    card.update(payload)
    card["badges"] = [
        {"label": "Otevřené eventy", "value": f"{int(payload.get('total_open_events', 0)):,}".replace(",", " ")},
        {"label": "Critical", "value": f"{int(payload.get('critical_count', 0)):,}".replace(",", " ")},
        {"label": "Vodoměry", "value": f"{int(payload.get('affected_devices', 0)):,}".replace(",", " ")},
    ]
    return card


def _load_manometry_chart_series(allowed_devices: tuple[str, ...], user_is_admin: bool) -> list[dict[str, object]]:
    now = prague_now_naive()
    cutoff = now - datetime.timedelta(hours=MANOMETRY_CHART_LOOKBACK_HOURS)

    session = get_session_ms()
    try:
        latest_devices_query = session.query(
            Mereni_manometry.identifikace,
            func.max(Mereni_manometry.date).label("last_measurement_at"),
        ).filter(
            Mereni_manometry.identifikace.is_not(None),
            Mereni_manometry.date.is_not(None),
            Mereni_manometry.hodnota.is_not(None),
            Mereni_manometry.date >= cutoff,
            Mereni_manometry.date <= now,
        )
        latest_devices_query = _apply_device_scope(
            latest_devices_query,
            Mereni_manometry.identifikace,
            allowed_devices,
            user_is_admin,
        )
        latest_devices = (
            latest_devices_query
            .group_by(Mereni_manometry.identifikace)
            .order_by(func.max(Mereni_manometry.date).desc(), Mereni_manometry.identifikace.asc())
            .limit(MANOMETRY_CHART_DEVICE_LIMIT)
            .all()
        )
        if not latest_devices:
            return []

        selected_idents = [str(row.identifikace) for row in latest_devices if row.identifikace]
        selected_ident_set = set(selected_idents)
        rows = session.query(
            Mereni_manometry.identifikace,
            Mereni_manometry.date,
            Mereni_manometry.hodnota,
            Mereni_manometry.platne,
        ).filter(
            Mereni_manometry.identifikace.in_(selected_idents),
            Mereni_manometry.date.is_not(None),
            Mereni_manometry.hodnota.is_not(None),
            Mereni_manometry.date >= cutoff,
            Mereni_manometry.date <= now,
        ).order_by(
            Mereni_manometry.identifikace.asc(),
            Mereni_manometry.date.asc(),
        ).all()

        rows_by_ident: dict[str, list[dict[str, object]]] = {ident: [] for ident in selected_idents}
        for row in rows:
            ident = str(row.identifikace)
            if ident not in selected_ident_set:
                continue
            rows_by_ident.setdefault(ident, []).append(
                {
                    "date": row.date,
                    "hodnota_bar": convert_pressure_value_to_bar(row.hodnota),
                    "platne": bool(row.platne) if row.platne is not None else None,
                }
            )

        chart_series: list[dict[str, object]] = []
        for latest_row in latest_devices:
            ident = str(latest_row.identifikace)
            series_rows = rows_by_ident.get(ident, [])
            device_detail = load_manometry_device_detail(ident, allowed_devices, user_is_admin) or {}
            chart_series.append(
                {
                    "identifikace": ident,
                    "last_measurement_at": latest_row.last_measurement_at,
                    "max_value_bar": device_detail.get("max_pressure"),
                    "max_value_at": device_detail.get("max_pressure_at"),
                    "min_value_bar": device_detail.get("min_pressure"),
                    "min_value_at": device_detail.get("min_pressure_at"),
                    "series_rows": series_rows,
                }
            )

        return chart_series
    finally:
        session.close()


def _load_manometry_card(allowed_devices: tuple[str, ...], user_is_admin: bool) -> dict[str, object]:
    metrics = _load_ms_measurement_metrics(
        measurement_model=Mereni_manometry,
        ident_column=Mereni_manometry.identifikace,
        date_column=Mereni_manometry.date,
        allowed_devices=allowed_devices,
        user_is_admin=user_is_admin,
        valid_column=Mereni_manometry.platne,
    )

    card = _build_empty_card(
        "manometry",
        accessible=True,
        description="Tlakové profily a validita měření napříč dostupnými manometry.",
    )
    card.update(metrics)
    card["total_devices"] = len(load_manometry_ident_options(allowed_devices, user_is_admin))
    card["chart_series"] = _load_manometry_chart_series(allowed_devices, user_is_admin)
    return card


def _load_plynomery_card(allowed_devices: tuple[str, ...], user_is_admin: bool) -> dict[str, object]:
    metrics = _load_ms_measurement_metrics(
        measurement_model=Plynomer_areal_Mereni,
        ident_column=Plynomer_areal_Mereni.identifikace,
        date_column=Plynomer_areal_Mereni.date,
        allowed_devices=allowed_devices,
        user_is_admin=user_is_admin,
        valid_column=Plynomer_areal_Mereni.platne,
    )

    card = _build_empty_card(
        "plynomery",
        accessible=True,
        description="Poslední odečty plynoměrů a kvalita načtených dat v posledním týdnu.",
    )
    card.update(metrics)
    card["total_devices"] = len(load_plynomery_ident_options(allowed_devices, user_is_admin))
    return card


def _load_elektromery_card(allowed_devices: tuple[str, ...], user_is_admin: bool) -> dict[str, object]:
    metrics = _load_ms_measurement_metrics(
        measurement_model=Elektromer_areal_Mereni,
        ident_column=Elektromer_areal_Mereni.identifikace,
        date_column=Elektromer_areal_Mereni.date,
        allowed_devices=allowed_devices,
        user_is_admin=user_is_admin,
    )

    card = _build_empty_card(
        "elektromery",
        accessible=True,
        description="Souhrn elektroměrů se zaměřením na čerstvost odečtů a pokrytí zařízení.",
    )
    card.update(metrics)
    card["total_devices"] = len(load_elektromery_ident_options(allowed_devices, user_is_admin))
    if int(card["recent_measurements"]) > 0:
        card["badges"] = [
            {"label": "Zařízení s daty", "value": f"{int(card['recent_devices']):,}".replace(",", " ")},
        ]
    return card


def _load_kalorimetry_card(allowed_devices: tuple[str, ...], user_is_admin: bool) -> dict[str, object]:
    metrics = _load_ms_measurement_metrics(
        measurement_model=Kalorimetr_areal_Mereni,
        ident_column=Kalorimetr_areal_Mereni.identifikace,
        date_column=Kalorimetr_areal_Mereni.date,
        allowed_devices=allowed_devices,
        user_is_admin=user_is_admin,
        valid_column=Kalorimetr_areal_Mereni.platne,
    )

    card = _build_empty_card(
        "kalorimetry",
        accessible=True,
        description="Přehled kalorimetrů a stavu posledních energetických odečtů.",
    )
    card.update(metrics)
    card["total_devices"] = len(load_kalorimetry_ident_options(allowed_devices, user_is_admin))
    return card


def _load_accessible_card(section_key: str, allowed_devices: tuple[str, ...], user_is_admin: bool) -> dict[str, object]:
    if section_key == "vodomery":
        return _load_vodomery_card(allowed_devices, user_is_admin)
    if section_key == "manometry":
        return _load_manometry_card(allowed_devices, user_is_admin)
    if section_key == "plynomery":
        return _load_plynomery_card(allowed_devices, user_is_admin)
    if section_key == "elektromery":
        return _load_elektromery_card(allowed_devices, user_is_admin)
    if section_key == "kalorimetry":
        return _load_kalorimetry_card(allowed_devices, user_is_admin)
    return _build_empty_card(section_key, accessible=True, description="Sekce zatím nemá overview loader.")


@st.cache_data(ttl=60)
def load_dashboard_overview_cards(
    accessible_sections: tuple[str, ...],
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> list[dict[str, object]]:
    accessible_set = set(accessible_sections)
    cards: list[dict[str, object]] = []

    for section in SECTIONS:
        if section.key not in accessible_set:
            cards.append(
                _build_empty_card(
                    section.key,
                    accessible=False,
                    description="Sekce není pro aktuální účet dostupná nebo nemá přiřazené zařízení.",
                )
            )
            continue

        try:
            cards.append(_load_accessible_card(section.key, allowed_devices, user_is_admin))
        except (DashboardApiError, SQLAlchemyError, ValueError) as exc:
            cards.append(
                _build_empty_card(
                    section.key,
                    accessible=True,
                    description="Data se zatím nepodařilo načíst. Přehledovou stránku modulu lze otevřít přímo.",
                    error=str(exc),
                )
            )

    vodomery_accessible = "vodomery" in accessible_set
    if not vodomery_accessible:
        cards.append(
            _build_empty_card(
                "vodomery_alarm",
                accessible=False,
                description="Sekce není pro aktuální účet dostupná nebo nemá přiřazené zařízení.",
                title="Vodoměry alarm",
                icon="🚨",
                accent_color="#dc2626",
                page_key="vodomery_anomalie_eventy",
            )
        )
        return cards

    try:
        cards.append(_load_vodomery_alarm_card(allowed_devices, user_is_admin))
    except (DashboardApiError, SQLAlchemyError, ValueError) as exc:
        cards.append(
            _build_empty_card(
                "vodomery_alarm",
                accessible=True,
                description="Data se zatím nepodařilo načíst. Stránku s anomaly eventy lze otevřít přímo.",
                error=str(exc),
                title="Vodoměry alarm",
                icon="🚨",
                accent_color="#dc2626",
                page_key="vodomery_anomalie_eventy",
            )
        )

    return cards
