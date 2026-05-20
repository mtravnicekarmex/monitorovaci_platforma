from __future__ import annotations

import datetime
from dataclasses import dataclass
import re
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, Numeric
from sqlalchemy.exc import SQLAlchemyError

from core.db.connect import get_session_ms
from moduly.apps.dashboard.auth import get_allowed_devices, is_admin
from moduly.apps.dashboard.vodomery_shared import render_page_styles
from moduly.mereni.elektromery.database.models import Elektromer_areal_Zarizeni
from moduly.mereni.kalorimetry.database.models import Kalorimetr_areal_Zarizeni
from moduly.mereni.manometry.database.models import Manometr_areal_Zarizeni
from moduly.mereni.plynomery.database.models import Plynomer_areal_Zarizeni
from moduly.mereni.vodomery.database.models import Vodomer_areal_Zarizeni


@dataclass(frozen=True)
class DeviceListColumn:
    attr: str
    label: str


@dataclass(frozen=True)
class DeviceListConfig:
    title: str
    source_table: str
    model: type[Any]
    columns: tuple[DeviceListColumn, ...]


@dataclass(frozen=True)
class DeviceCreateField:
    attr: str
    label: str
    required: bool
    placeholder: str


DEVICE_LIST_CONFIGS: dict[str, DeviceListConfig] = {
    "vodomery": DeviceListConfig(
        title="Seznam vodoměrů",
        source_table="dbo.Zarizeni_vodomery",
        model=Vodomer_areal_Zarizeni,
        columns=(
            DeviceListColumn("identifikace", "Identifikace"),
            DeviceListColumn("seriove_cislo", "Sériové číslo"),
            DeviceListColumn("MBUS", "MBUS"),
            DeviceListColumn("pozice", "Pozice"),
            DeviceListColumn("podruzny", "Podružný"),
            DeviceListColumn("mistnost", "Místnost"),
            DeviceListColumn("objekt", "Objekt"),
            DeviceListColumn("patro", "Patro"),
            DeviceListColumn("umisteni", "Umístění"),
            DeviceListColumn("napaji", "Napájí"),
            DeviceListColumn("koncovy_odberatel", "Koncový odběratel"),
            DeviceListColumn("platnost_cejchu", "Platnost cejchu"),
            DeviceListColumn("redukcni_ventil", "Redukční ventil"),
            DeviceListColumn("filtr", "Filtr"),
            DeviceListColumn("poznamka_vodomery", "Poznámka"),
            DeviceListColumn("foto", "Foto"),
        ),
    ),
    "plynomery": DeviceListConfig(
        title="Seznam plynoměrů",
        source_table="dbo.Zarizeni_plynomery",
        model=Plynomer_areal_Zarizeni,
        columns=(
            DeviceListColumn("identifikace", "Identifikace"),
            DeviceListColumn("seriove_cislo", "Sériové číslo"),
            DeviceListColumn("MBUS", "MBUS"),
            DeviceListColumn("pozice", "Pozice"),
            DeviceListColumn("podruzny", "Podružný"),
            DeviceListColumn("mistnost", "Místnost"),
            DeviceListColumn("objekt", "Objekt"),
            DeviceListColumn("patro", "Patro"),
            DeviceListColumn("umisteni", "Umístění"),
            DeviceListColumn("napaji", "Napájí"),
            DeviceListColumn("koncovy_odberatel", "Koncový odběratel"),
            DeviceListColumn("platnost_cejchu", "Platnost cejchu"),
            DeviceListColumn("poznamka_plynomery", "Poznámka"),
            DeviceListColumn("foto", "Foto"),
        ),
    ),
    "elektromery": DeviceListConfig(
        title="Seznam elektroměrů",
        source_table="dbo.Zarizeni_elektromery",
        model=Elektromer_areal_Zarizeni,
        columns=(
            DeviceListColumn("identifikace", "Identifikace"),
            DeviceListColumn("seriove_cislo", "Sériové číslo"),
            DeviceListColumn("softlink_id", "SOFTLINK ID"),
            DeviceListColumn("EAN", "EAN"),
            DeviceListColumn("pozice", "Pozice"),
            DeviceListColumn("podruzny", "Podružný"),
            DeviceListColumn("mistnost", "Místnost"),
            DeviceListColumn("umisteni", "Umístění"),
            DeviceListColumn("napaji", "Napájí"),
            DeviceListColumn("koncovy_odberatel", "Koncový odběratel"),
            DeviceListColumn("platnost_cejchu", "Platnost cejchu"),
            DeviceListColumn("jistic", "Jistič"),
            DeviceListColumn("typ_merice", "Typ měřiče"),
            DeviceListColumn("rozvadec", "Rozvaděč"),
            DeviceListColumn("typ_tarifu", "Typ tarifu"),
            DeviceListColumn("platnost_od", "Platnost od"),
            DeviceListColumn("platnost_do", "Platnost do"),
            DeviceListColumn("plomb", "Plomba"),
            DeviceListColumn("mis_id", "MIS ID"),
            DeviceListColumn("met_id", "MET ID"),
            DeviceListColumn("foto", "Foto"),
        ),
    ),
    "kalorimetry": DeviceListConfig(
        title="Seznam kalorimetrů",
        source_table="dbo.Zarizeni_kalorimetry",
        model=Kalorimetr_areal_Zarizeni,
        columns=(
            DeviceListColumn("identifikace", "Identifikace"),
            DeviceListColumn("seriove_cislo", "Sériové číslo"),
            DeviceListColumn("MBUS", "MBUS"),
            DeviceListColumn("objekt", "Objekt"),
            DeviceListColumn("patro", "Patro"),
            DeviceListColumn("mistnost", "Místnost"),
            DeviceListColumn("umisteni", "Umístění"),
            DeviceListColumn("napaji", "Napájí"),
            DeviceListColumn("zdroj", "Zdroj"),
            DeviceListColumn("zdroj_mereni", "Zdroj měření"),
            DeviceListColumn("koncovy_odberatel", "Koncový odběratel"),
            DeviceListColumn("platnost_cejchu", "Platnost cejchu"),
            DeviceListColumn("poznamka_kalorimetry", "Poznámka"),
            DeviceListColumn("foto", "Foto"),
        ),
    ),
    "manometry": DeviceListConfig(
        title="Seznam manometrů",
        source_table="dbo.Zarizeni_manometry",
        model=Manometr_areal_Zarizeni,
        columns=(
            DeviceListColumn("id", "ID"),
            DeviceListColumn("identifikace", "Identifikace"),
            DeviceListColumn("seriove_cislo", "Sériové číslo"),
            DeviceListColumn("objekt", "Objekt"),
            DeviceListColumn("patro", "Patro"),
            DeviceListColumn("mistnost", "Místnost"),
            DeviceListColumn("vetev", "Větev"),
            DeviceListColumn("foto", "Foto"),
        ),
    ),
}


def _format_display_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, datetime.date):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, bool):
        return "ANO" if value else "NE"
    return value


def _is_auto_primary_key(model: type[Any], attr: str) -> bool:
    column = model.__table__.columns[attr]
    return bool(column.primary_key and attr == "id")


def _primary_key_attr(model: type[Any]) -> str:
    primary_key_columns = tuple(model.__table__.primary_key.columns)
    if len(primary_key_columns) != 1:
        raise ValueError(f"Tabulka {model.__tablename__} nema jednoduchy primarni klic.")
    return str(primary_key_columns[0].key)


def _is_required_form_field(model: type[Any], attr: str) -> bool:
    column = model.__table__.columns[attr]
    return not bool(column.nullable) and column.default is None and column.server_default is None


def _field_placeholder(model: type[Any], attr: str) -> str:
    column_type = model.__table__.columns[attr].type
    if isinstance(column_type, (Integer, BigInteger)):
        return "Celé číslo"
    if isinstance(column_type, (Float, Numeric)):
        return "Číslo"
    if isinstance(column_type, DateTime):
        return "DD.MM.RRRR nebo DD.MM.RRRR HH:MM"
    if isinstance(column_type, Boolean):
        return "ANO / NE"
    return ""


def build_create_fields(config: DeviceListConfig) -> tuple[DeviceCreateField, ...]:
    fields: list[DeviceCreateField] = []
    for column in config.columns:
        if _is_auto_primary_key(config.model, column.attr):
            continue
        fields.append(
            DeviceCreateField(
                attr=column.attr,
                label=column.label,
                required=_is_required_form_field(config.model, column.attr),
                placeholder=_field_placeholder(config.model, column.attr),
            )
        )
    return tuple(fields)


def build_edit_fields(config: DeviceListConfig) -> tuple[DeviceCreateField, ...]:
    primary_key_attr = _primary_key_attr(config.model)
    return tuple(
        field
        for field in build_create_fields(config)
        if field.attr != primary_key_attr
    )


def _format_form_initial_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, datetime.date):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, bool):
        return "ANO" if value else "NE"
    return str(value)


def _form_key_fragment(value: object) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", str(value))[:80] or "record"


def _coerce_form_value(model: type[Any], attr: str, raw_value: object) -> object:
    column = model.__table__.columns[attr]
    text_value = "" if raw_value is None else str(raw_value).strip()
    if not text_value:
        if _is_required_form_field(model, attr):
            raise ValueError(f"Pole {attr} je povinné.")
        return None

    column_type = column.type
    if isinstance(column_type, (Integer, BigInteger)):
        try:
            return int(text_value.replace(" ", ""))
        except ValueError as exc:
            raise ValueError(f"Pole {attr} musí být celé číslo.") from exc

    if isinstance(column_type, (Float, Numeric)):
        try:
            return float(text_value.replace(" ", "").replace(",", "."))
        except ValueError as exc:
            raise ValueError(f"Pole {attr} musí být číslo.") from exc

    if isinstance(column_type, DateTime):
        parsed_value = pd.to_datetime(text_value, dayfirst=True, errors="coerce")
        if pd.isna(parsed_value):
            raise ValueError(f"Pole {attr} nemá platný formát data.")
        return parsed_value.to_pydatetime()

    if isinstance(column_type, Boolean):
        normalized_value = text_value.lower()
        if normalized_value in {"ano", "a", "true", "1", "yes", "y"}:
            return True
        if normalized_value in {"ne", "n", "false", "0", "no"}:
            return False
        raise ValueError(f"Pole {attr} musí být ANO nebo NE.")

    return text_value


def _filter_dataframe(df: pd.DataFrame, search_query: str) -> pd.DataFrame:
    normalized_query = search_query.strip()
    if not normalized_query or df.empty:
        return df

    haystack = df.astype(str).apply(lambda row: " ".join(row.values).lower(), axis=1)
    return df.loc[haystack.str.contains(normalized_query.lower(), regex=False, na=False)].copy()


@st.cache_data(ttl=60)
def load_device_list(
    meter_key: str,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> pd.DataFrame:
    config = DEVICE_LIST_CONFIGS[meter_key]
    selected_columns = [getattr(config.model, column.attr) for column in config.columns]

    session = get_session_ms()
    try:
        query = session.query(*selected_columns)
        if not user_is_admin:
            if not allowed_devices:
                return pd.DataFrame(columns=[column.label for column in config.columns])
            query = query.filter(config.model.identifikace.in_(allowed_devices))
        query = query.order_by(config.model.identifikace.asc())
        rows = query.all()
    finally:
        session.close()

    records = [
        {
            column.label: _format_display_value(value)
            for column, value in zip(config.columns, tuple(row), strict=True)
        }
        for row in rows
    ]
    return pd.DataFrame(records, columns=[column.label for column in config.columns])


@st.cache_data(ttl=60)
def load_device_identity_options(
    meter_key: str,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> tuple[tuple[object, str], ...]:
    config = DEVICE_LIST_CONFIGS[meter_key]
    primary_key_attr = _primary_key_attr(config.model)
    selected_columns = [getattr(config.model, primary_key_attr)]
    has_identifikace = hasattr(config.model, "identifikace")
    has_seriove_cislo = hasattr(config.model, "seriove_cislo")
    if has_identifikace and primary_key_attr != "identifikace":
        selected_columns.append(config.model.identifikace)
    if has_seriove_cislo and primary_key_attr != "seriove_cislo":
        selected_columns.append(config.model.seriove_cislo)

    session = get_session_ms()
    try:
        query = session.query(*selected_columns)
        if not user_is_admin:
            if not allowed_devices:
                return ()
            query = query.filter(config.model.identifikace.in_(allowed_devices))
        order_column = config.model.identifikace if has_identifikace else getattr(config.model, primary_key_attr)
        rows = query.order_by(order_column.asc()).all()
    finally:
        session.close()

    options: list[tuple[object, str]] = []
    for row in rows:
        values = tuple(row)
        primary_key_value = values[0]
        label_parts = [str(value) for value in values[1:] if value not in {None, ""}]
        if label_parts:
            label = f"{' | '.join(label_parts)} | {primary_key_attr}: {primary_key_value}"
        else:
            label = str(primary_key_value)
        options.append((primary_key_value, label))
    return tuple(options)


@st.cache_data(ttl=60)
def load_device_record_values(
    meter_key: str,
    primary_key_value: object,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> dict[str, object] | None:
    config = DEVICE_LIST_CONFIGS[meter_key]
    primary_key_attr = _primary_key_attr(config.model)
    selected_columns = [getattr(config.model, column.attr) for column in config.columns]

    session = get_session_ms()
    try:
        query = session.query(*selected_columns).filter(getattr(config.model, primary_key_attr) == primary_key_value)
        if not user_is_admin:
            if not allowed_devices:
                return None
            query = query.filter(config.model.identifikace.in_(allowed_devices))
        row = query.one_or_none()
    finally:
        session.close()

    if row is None:
        return None
    return {
        column.attr: value
        for column, value in zip(config.columns, tuple(row), strict=True)
    }


def create_device_record(meter_key: str, form_values: dict[str, object], *, user_is_admin: bool) -> None:
    if not user_is_admin:
        raise PermissionError("Nové zařízení může vytvořit pouze admin.")

    config = DEVICE_LIST_CONFIGS[meter_key]
    fields = build_create_fields(config)
    payload = {
        field.attr: _coerce_form_value(config.model, field.attr, form_values.get(field.attr))
        for field in fields
    }

    session = get_session_ms()
    try:
        session.add(config.model(**payload))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_device_record(
    meter_key: str,
    primary_key_value: object,
    form_values: dict[str, object],
    *,
    user_is_admin: bool,
) -> None:
    if not user_is_admin:
        raise PermissionError("Zařízení může upravit pouze admin.")

    config = DEVICE_LIST_CONFIGS[meter_key]
    primary_key_attr = _primary_key_attr(config.model)
    fields = build_edit_fields(config)
    payload = {
        field.attr: _coerce_form_value(config.model, field.attr, form_values.get(field.attr))
        for field in fields
    }

    session = get_session_ms()
    try:
        record = session.get(config.model, primary_key_value)
        if record is None:
            raise ValueError(f"Záznam s {primary_key_attr}={primary_key_value} nebyl nalezen.")
        for attr, value in payload.items():
            setattr(record, attr, value)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _render_create_device_form(meter_key: str, user_is_admin: bool) -> None:
    config = DEVICE_LIST_CONFIGS[meter_key]
    fields = build_create_fields(config)
    form_values: dict[str, object] = {}

    with st.form(f"{meter_key}_device_create_form"):
        st.subheader("Nová položka")
        field_columns = st.columns(2)
        for index, field in enumerate(fields):
            field_label = f"{field.label} *" if field.required else field.label
            with field_columns[index % 2]:
                form_values[field.attr] = st.text_input(
                    field_label,
                    key=f"{meter_key}_device_create_{field.attr}",
                    placeholder=field.placeholder,
                )
        submitted = st.form_submit_button("Uložit do DB", type="primary", width="stretch")

    if not submitted:
        return

    try:
        create_device_record(meter_key, form_values, user_is_admin=user_is_admin)
    except PermissionError as exc:
        st.error(str(exc))
    except ValueError as exc:
        st.warning(str(exc))
    except SQLAlchemyError as exc:
        st.error("Novou položku se nepodařilo uložit do MS SQL.")
        st.exception(exc)
    else:
        load_device_list.clear()
        st.session_state[f"{meter_key}_device_list_create_open"] = False
        st.session_state[f"{meter_key}_device_list_success"] = "Nová položka byla uložena do MS SQL."
        st.rerun()


def _clear_device_list_caches() -> None:
    load_device_list.clear()
    load_device_identity_options.clear()
    load_device_record_values.clear()


def _render_edit_device_form(
    meter_key: str,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> None:
    config = DEVICE_LIST_CONFIGS[meter_key]
    options = load_device_identity_options(meter_key, allowed_devices, user_is_admin)
    if not options:
        st.info("Není dostupný žádný záznam k úpravě.")
        return

    st.subheader("Upravit položku")
    selected_option = st.selectbox(
        "Zařízení",
        options=list(options),
        format_func=lambda option: str(option[1]),
        key=f"{meter_key}_device_edit_selected",
    )
    primary_key_value = selected_option[0]
    record_values = load_device_record_values(meter_key, primary_key_value, allowed_devices, user_is_admin)
    if record_values is None:
        st.warning("Vybraný záznam už není dostupný.")
        return

    fields = build_edit_fields(config)
    form_values: dict[str, object] = {}
    key_fragment = _form_key_fragment(primary_key_value)
    with st.form(f"{meter_key}_device_edit_form_{key_fragment}"):
        field_columns = st.columns(2)
        for index, field in enumerate(fields):
            field_label = f"{field.label} *" if field.required else field.label
            with field_columns[index % 2]:
                form_values[field.attr] = st.text_input(
                    field_label,
                    value=_format_form_initial_value(record_values.get(field.attr)),
                    key=f"{meter_key}_device_edit_{key_fragment}_{field.attr}",
                    placeholder=field.placeholder,
                )
        submitted = st.form_submit_button("Uložit změny", type="primary", width="stretch")

    if not submitted:
        return

    try:
        update_device_record(meter_key, primary_key_value, form_values, user_is_admin=user_is_admin)
    except PermissionError as exc:
        st.error(str(exc))
    except ValueError as exc:
        st.warning(str(exc))
    except SQLAlchemyError as exc:
        st.error("Změny se nepodařilo uložit do MS SQL.")
        st.exception(exc)
    else:
        _clear_device_list_caches()
        st.session_state[f"{meter_key}_device_list_edit_open"] = False
        st.session_state[f"{meter_key}_device_list_success"] = "Změny byly uloženy do MS SQL."
        st.rerun()


def render_device_list_page(meter_key: str) -> None:
    config = DEVICE_LIST_CONFIGS[meter_key]
    user_is_admin = is_admin()
    allowed_devices = get_allowed_devices()

    render_page_styles()
    st.title(config.title)
    st.caption(f"Zdroj: MS SQL `{config.source_table}`")
    success_message_key = f"{meter_key}_device_list_success"
    success_message = st.session_state.pop(success_message_key, None)
    if success_message:
        st.success(str(success_message))

    device_df = load_device_list(meter_key, allowed_devices, user_is_admin)
    search_query = st.text_input("Hledat", key=f"{meter_key}_device_list_search")
    visible_df = _filter_dataframe(device_df, search_query)

    metric_cols = st.columns(3)
    metric_cols[0].metric("Zařízení", len(device_df))
    metric_cols[1].metric("Zobrazeno", len(visible_df))
    metric_cols[2].metric("Přístup", "Všechna zařízení" if user_is_admin else f"{len(allowed_devices)} povolených")

    if visible_df.empty:
        st.info("Pro aktuální výběr nejsou v MS databázi žádná zařízení.")
    else:
        st.dataframe(visible_df, width="stretch", hide_index=True)

    create_open_key = f"{meter_key}_device_list_create_open"
    edit_open_key = f"{meter_key}_device_list_edit_open"
    action_cols = st.columns((1, 1, 4))
    with action_cols[0]:
        if st.button(
            "Přidat nový",
            type="primary",
            width="stretch",
            disabled=not user_is_admin,
            help=None if user_is_admin else "Nové zařízení může vytvořit pouze admin.",
        ):
            st.session_state[create_open_key] = True
            st.session_state[edit_open_key] = False
    with action_cols[1]:
        if st.button(
            "Upravit",
            width="stretch",
            disabled=not user_is_admin or device_df.empty,
            help=None if user_is_admin else "Zařízení může upravit pouze admin.",
        ):
            st.session_state[edit_open_key] = True
            st.session_state[create_open_key] = False

    if st.session_state.get(create_open_key, False):
        _render_create_device_form(meter_key, user_is_admin)
    if st.session_state.get(edit_open_key, False):
        _render_edit_device_form(meter_key, allowed_devices, user_is_admin)
