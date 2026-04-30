from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.vodomery_shared import render_page_styles
from moduly.mereni.elektromery.SOFTLINK.SOFTLINK_data_zarizeni import SOFTLINK_dotaz_zarizeni
from moduly.mereni.elektromery.softlink_devices import (
    ElektromerySoftlinkDeviceError,
    SoftlinkDeviceCandidate,
    SoftlinkDeviceDiscoveryReport,
    build_candidate_form_defaults,
    describe_candidate,
    discover_new_softlink_devices,
    save_new_softlink_device,
)


REPORT_STATE_KEY = "elektromery_new_devices_report"
FLASH_STATE_KEY = "elektromery_new_devices_flash"


st.set_page_config(
    page_title="Elektroměry - Nové elektroměry",
    page_icon="🆕",
    layout="wide",
)


require_page_access("elektromery_new_devices")


def _format_value(value: object) -> str:
    if value is None:
        return "-"
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y")
    text = str(value).strip()
    return text or "-"


def _render_flash_message() -> None:
    flash = st.session_state.pop(FLASH_STATE_KEY, None)
    if not isinstance(flash, dict):
        return
    level = str(flash.get("level") or "info")
    message = str(flash.get("message") or "").strip()
    if not message:
        return
    getattr(st, level, st.info)(message)


def _build_summary_dataframe(report: SoftlinkDeviceDiscoveryReport) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Softlink ID": device.softlink_id,
                "Popis": device.description,
                "Sériové číslo": device.serial_number,
                "Typ měřiče": device.meter_type,
                "MIS ID": device.mis_id,
                "MET ID": device.met_id,
                "Platnost od": device.valid_from,
                "Platnost do": device.valid_to,
                "Platnost cejchu": device.calibration_valid_until,
            }
            for device in report.new_devices
        ]
    )


def _build_source_dataframe(candidate: SoftlinkDeviceCandidate) -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Softlink ID", _format_value(candidate.softlink_id)),
            ("Popis ze SOFTLINK", _format_value(candidate.description)),
            ("Sériové číslo", _format_value(candidate.serial_number)),
            ("Typ měřiče", _format_value(candidate.meter_type)),
            ("Plomb", _format_value(candidate.plomb)),
            ("Počáteční stav", _format_value(candidate.initial_value)),
            ("MIS ID", _format_value(candidate.mis_id)),
            ("MET ID", _format_value(candidate.met_id)),
            ("Platnost od", _format_value(candidate.valid_from)),
            ("Platnost do", _format_value(candidate.valid_to)),
            ("Platnost cejchu", _format_value(candidate.calibration_valid_until)),
        ],
        columns=["Pole", "Hodnota"],
    )


def _render_candidate_form(candidate: SoftlinkDeviceCandidate) -> None:
    defaults = build_candidate_form_defaults(candidate)
    with st.expander(f"{candidate.softlink_id} | {describe_candidate(candidate)}", expanded=False):
        top_cols = st.columns((1.2, 2.4))
        with top_cols[0]:
            st.dataframe(_build_source_dataframe(candidate), width="stretch", hide_index=True)
        with top_cols[1]:
            with st.form(f"elektromery_new_device_{candidate.softlink_id}"):
                row_1 = st.columns(3)
                row_2 = st.columns(3)
                row_3 = st.columns(3)
                row_4 = st.columns(3)
                row_5 = st.columns(3)
                row_6 = st.columns(3)
                row_7 = st.columns(2)

                identifikace = row_1[0].text_input("Identifikace", value=str(defaults["identifikace"]))
                seriove_cislo = row_1[1].text_input("Sériové číslo", value=str(defaults["seriove_cislo"]))
                ean = row_1[2].text_input("EAN", value=str(defaults["ean"]))

                pozice = row_2[0].text_input("Pozice", value=str(defaults["pozice"]))
                podruzny = row_2[1].text_input("Podružný", value=str(defaults["podruzny"]))
                mistnost = row_2[2].text_input("Místnost", value=str(defaults["mistnost"]))

                umisteni = row_3[0].text_input("Umístění", value=str(defaults["umisteni"]))
                napaji = row_3[1].text_input("Napájí", value=str(defaults["napaji"]))
                koncovy_odberatel = row_3[2].text_input(
                    "Koncový odběratel",
                    value=str(defaults["koncovy_odberatel"]),
                )

                platnost_cejchu = row_4[0].text_input("Platnost cejchu", value=str(defaults["platnost_cejchu"]))
                jistic = row_4[1].text_input("Jistič", value=str(defaults["jistic"]))
                typ_merice = row_4[2].text_input("Typ měřiče", value=str(defaults["typ_merice"]))

                rozvadec = row_5[0].text_input("Rozvaděč", value=str(defaults["rozvadec"]))
                typ_tarifu = row_5[1].text_input("Typ tarifu", value=str(defaults["typ_tarifu"]))
                plomb = row_5[2].text_input("Plomb", value=str(defaults["plomb"]))

                platnost_od = row_6[0].text_input("Platnost od", value=str(defaults["platnost_od"]))
                platnost_do = row_6[1].text_input("Platnost do", value=str(defaults["platnost_do"]))
                foto = row_6[2].text_input("Foto", value=str(defaults["foto"]))

                mis_id = row_7[0].text_input("MIS ID", value=str(defaults["mis_id"]))
                met_id = row_7[1].text_input("MET ID", value=str(defaults["met_id"]))

                submitted = st.form_submit_button("Uložit do MS DB", type="primary", width="stretch")

            if not submitted:
                return

            try:
                save_result = save_new_softlink_device(
                    candidate,
                    {
                        "identifikace": identifikace,
                        "seriove_cislo": seriove_cislo,
                        "ean": ean,
                        "pozice": pozice,
                        "podruzny": podruzny,
                        "mistnost": mistnost,
                        "umisteni": umisteni,
                        "napaji": napaji,
                        "koncovy_odberatel": koncovy_odberatel,
                        "platnost_cejchu": platnost_cejchu,
                        "jistic": jistic,
                        "typ_merice": typ_merice,
                        "rozvadec": rozvadec,
                        "typ_tarifu": typ_tarifu,
                        "platnost_od": platnost_od,
                        "platnost_do": platnost_do,
                        "plomb": plomb,
                        "mis_id": mis_id,
                        "met_id": met_id,
                        "foto": foto,
                    },
                )
            except ElektromerySoftlinkDeviceError as exc:
                st.error(str(exc))
                return

            current_report = st.session_state.get(REPORT_STATE_KEY)
            if isinstance(current_report, SoftlinkDeviceDiscoveryReport):
                st.session_state[REPORT_STATE_KEY] = current_report.remove_device(candidate.softlink_id)

            action_label = {
                "inserted": "vložen",
                "updated": "aktualizován",
                "already_exists": "už byl mezitím založen",
            }.get(save_result.action, save_result.action)
            st.session_state[FLASH_STATE_KEY] = {
                "level": "success",
                "message": (
                    f"Záznam {save_result.identifikace} (softlink_id {save_result.softlink_id}) byl {action_label}."
                ),
            }
            st.rerun()


def render_dashboard() -> None:
    render_page_styles()
    st.title("Nové elektroměry")
    st.caption("Kontrola nových zařízení ze SOFTLINK a doplnění chybějících míst do `dbo.Zarizeni_elektromery`.")
    _render_flash_message()

    action_cols = st.columns((1.3, 4.7))
    with action_cols[0]:
        refresh_pressed = st.button("Načíst ze SOFTLINK", type="primary", width="stretch")

    if refresh_pressed:
        with st.spinner("Načítám zařízení ze SOFTLINK a porovnávám je s MS databází..."):
            st.session_state[REPORT_STATE_KEY] = discover_new_softlink_devices(
                fetch_fn=lambda: SOFTLINK_dotaz_zarizeni(
                    headless=True,
                    timeout_ms=180000,
                    retry_headful_on_timeout=True,
                ),
            )

    report = st.session_state.get(REPORT_STATE_KEY)
    if report is None:
        st.info("Pro načtení seznamu nových zařízení spusťte kontrolu ze SOFTLINK.")
        return
    if not isinstance(report, SoftlinkDeviceDiscoveryReport):
        st.warning("V session není platný report nových zařízení. Spusťte kontrolu znovu.")
        return

    metric_cols = st.columns(4)
    metric_cols[0].metric("Zařízení v SOFTLINK", report.total_softlink_devices)
    metric_cols[1].metric("Spárovaná v MS DB", report.matched_device_count)
    metric_cols[2].metric("Nová softlink_id", report.new_device_count)
    metric_cols[3].metric("Zdrojová odpověď", report.source_status or "-")
    st.caption(f"Naposledy načteno: {_format_value(report.generated_at)}")

    if not report.new_devices:
        st.success("V SOFTLINK nejsou žádná nová zařízení mimo `dbo.Zarizeni_elektromery`.")
        return

    st.subheader("Seznam nových zařízení")
    st.dataframe(_build_summary_dataframe(report), width="stretch", hide_index=True)

    st.subheader("Doplnění do MS DB")
    for candidate in report.new_devices:
        _render_candidate_form(candidate)


try:
    render_dashboard()
except ElektromerySoftlinkDeviceError as exc:
    st.error(str(exc))
