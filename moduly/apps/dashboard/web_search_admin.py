from __future__ import annotations

from datetime import datetime

import streamlit as st

from moduly.apps.dashboard.api_client import (
    DashboardApiError,
    create_web_search_monitor as api_create_web_search_monitor,
    delete_web_search_monitor as api_delete_web_search_monitor,
    list_web_search_monitors as api_list_web_search_monitors,
    list_web_search_results as api_list_web_search_results,
    preview_web_search_hits as api_preview_web_search_hits,
    update_web_search_monitor as api_update_web_search_monitor,
)
from moduly.apps.dashboard.auth import get_auth_token


PREVIEW_STATE_KEY = "web_search_preview_hits"
RESULTS_LIMIT = 200


def _require_access_token() -> str:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybí bearer token pro dashboard API.")
    return access_token


def _normalize_expressions(raw_value: str) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_value.split(","):
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _format_timestamp(value: object) -> str:
    if value in (None, ""):
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        return parsed.strftime("%d.%m.%Y %H:%M")
    return str(value)


def _clear_web_search_cache() -> None:
    load_monitors.clear()
    load_results.clear()


@st.cache_data(ttl=60)
def load_monitors(access_token: str) -> list[dict[str, object]]:
    return api_list_web_search_monitors(access_token)


@st.cache_data(ttl=60)
def load_results(access_token: str, limit: int = RESULTS_LIMIT) -> list[dict[str, object]]:
    return api_list_web_search_results(access_token, limit=limit)


def _render_preview_hits(hits: list[dict[str, object]]) -> None:
    if not hits:
        st.info("Žádné nové výskyty.")
        return
    for hit in hits:
        vyraz = str(hit.get("vyraz") or "")
        snippet = hit.get("snippet")
        odkaz = hit.get("odkaz")
        if odkaz:
            st.markdown(f'- **"{vyraz}"**: [Otevřít odkaz]({odkaz})')
        else:
            st.markdown(f"- **{vyraz}**: …{snippet or ''}…")


def _render_results(results: list[dict[str, object]]) -> None:
    if not results:
        st.info("Žádné záznamy v historii.")
        return
    for row in results:
        vyraz = str(row.get("vyraz") or "")
        datum_str = _format_timestamp(row.get("datum"))
        monitor_url = str(row.get("monitor_url") or row.get("url") or "Nedefinovaný monitor")
        odkaz = row.get("odkaz")
        snippet = row.get("snippet")
        if odkaz:
            st.markdown(f'- **"{vyraz}"** na {monitor_url} - [Otevřít odkaz]({odkaz}) ({datum_str})')
        elif snippet:
            st.markdown(f"- **{vyraz}** na [{monitor_url}]({monitor_url}) ({datum_str}): …{snippet}…")
        else:
            st.markdown(f"- **{vyraz}** na [{monitor_url}]({monitor_url}) ({datum_str})")


def render_web_search_admin_page() -> None:
    access_token = _require_access_token()

    st.title("Monitor webových stránek")
    st.caption(
        "Admin rozhraní pro správu monitorů a ruční preview hledaných výrazů. "
        "Dashboard používá pouze API přístup."
    )
    st.caption("Automatické odesílání upozornění běží podle aktuální konfigurace scheduleru.")

    monitors = load_monitors(access_token)
    results = load_results(access_token)

    st.session_state.setdefault(PREVIEW_STATE_KEY, [])

    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            url = st.text_input("Zadat URL", key="web_search_url")
            expressions_raw = st.text_input(
                "Hledané výrazy (oddělené čárkou)",
                key="web_search_expressions",
            )
        with col2:
            email = st.text_input(
                "Email pro zasílání upozornění",
                key="web_search_email",
            )

        preview_col, save_col = st.columns(2)
        if preview_col.button("Hledat nyní", key="web_search_preview_button"):
            preview_payload = {
                "url": url,
                "expressions": _normalize_expressions(expressions_raw),
            }
            preview_response = api_preview_web_search_hits(access_token, preview_payload)
            st.session_state[PREVIEW_STATE_KEY] = list(preview_response.get("hits", []))

        if save_col.button("Uložit monitor", key="web_search_save_button"):
            response = api_create_web_search_monitor(
                access_token,
                {
                    "url": url,
                    "email": email,
                    "expressions": _normalize_expressions(expressions_raw),
                },
            )
            added_expressions = [str(item) for item in response.get("added_expressions", [])]
            if response.get("created"):
                st.success("Nový monitor uložen!")
            elif added_expressions:
                st.success(f"Aktualizován monitor, přidány nové výrazy: {', '.join(added_expressions)}")
            else:
                st.info("Tento monitor již obsahuje všechny zadané výrazy.")
            _clear_web_search_cache()
            st.rerun()

    preview_history_col, history_col = st.columns(2)

    with preview_history_col:
        st.markdown("---")
        st.write("📌 Okamžité hledání nových výskytů:")
        _render_preview_hits(list(st.session_state.get(PREVIEW_STATE_KEY, [])))

    with history_col:
        st.markdown("---")
        st.write(f"📌 Historie všech výskytů (posledních {RESULTS_LIMIT}):")
        _render_results(results)

    st.markdown("---")
    st.write("⚙️ Správa monitorů")

    if not monitors:
        st.info("Žádné uložené monitory.")
        return

    for monitor in monitors:
        monitor_id = int(monitor["id"])
        with st.expander(f"🌐 {monitor['url']}"):
            st.caption(
                f"Vytvořeno: {_format_timestamp(monitor.get('created'))} | "
                f"Poslední běh: {_format_timestamp(monitor.get('last_run'))} | "
                f"Výsledků v historii: {int(monitor.get('results_count') or 0)}"
            )
            with st.form(key=f"web_search_monitor_form_{monitor_id}"):
                edit_col1, edit_col2 = st.columns(2)
                with edit_col1:
                    new_url = st.text_input("URL", value=str(monitor["url"]), key=f"monitor_url_{monitor_id}")
                    new_expressions = st.text_input(
                        "Hledané výrazy (oddělené čárkou)",
                        value=", ".join(str(item) for item in monitor.get("expressions", [])),
                        key=f"monitor_expressions_{monitor_id}",
                    )
                with edit_col2:
                    new_email = st.text_input(
                        "Email",
                        value=str(monitor["email"]),
                        key=f"monitor_email_{monitor_id}",
                    )

                save_form_col, delete_form_col = st.columns(2)
                save_pressed = save_form_col.form_submit_button("💾 Uložit změny")
                confirm_delete = st.checkbox(
                    "Opravdu smazat tento monitor?",
                    key=f"monitor_confirm_delete_{monitor_id}",
                )
                delete_pressed = delete_form_col.form_submit_button("🗑 Smazat monitor")

                if save_pressed:
                    api_update_web_search_monitor(
                        access_token,
                        monitor_id,
                        {
                            "url": new_url,
                            "email": new_email,
                            "expressions": _normalize_expressions(new_expressions),
                        },
                    )
                    st.success("Monitor upraven.")
                    _clear_web_search_cache()
                    st.rerun()

                if delete_pressed and confirm_delete:
                    api_delete_web_search_monitor(access_token, monitor_id)
                    st.warning("Monitor smazán.")
                    _clear_web_search_cache()
                    st.rerun()
