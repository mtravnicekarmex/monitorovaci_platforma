import logging
import json

import streamlit as st

from core.db.connect import get_session_pg
from moduly.apps.web_search.database.models import Monitor, Result
from moduly.apps.web_search.service import (
    find_matching_monitor,
    hledat_nove_vyskyt,
    normalize_expressions,
    normalize_monitor_url,
)


logger = logging.getLogger(__name__)




# -------------------------
# Streamlit UI
# -------------------------
st.set_page_config(
    page_title = 'Monitor webových stránek',
    page_icon = '🔍',
    layout="wide")


with st.container():
    st.subheader("Monitor webových stránek")
    st.write("Upozornění na nové výskyty hledaných výrazů z vybraných webových stránek jsou odesílána e‑mailem každý den v 6:00 a 14:00.")

    col1, col2 = st.columns(2)

    with col1:
        url = st.text_input("Zadat URL")
        vyrazy = st.text_input("Hledané výrazy (oddělené čárkou)")



    with col2:
        # frequency = st.selectbox("Frekvence reportu", ["denně", "týdně", "měsíčně"])
        email = st.text_input("Email pro zasílání upozornění")




    col3, col4 = st.columns(2)
    with col3:
        if st.button("Hledat nyní"):
            if not url or not vyrazy:
                st.warning("Zadej URL a hledané výrazy!")
            else:
                normalized_url = normalize_monitor_url(url)
                vyrazy_list = normalize_expressions(vyrazy.split(","))
                if not normalized_url:
                    st.warning("Zadej platnou URL.")
                elif not vyrazy_list:
                    st.warning("Zadej alespoň jeden platný výraz.")
                else:
                    session = get_session_pg()
                    temp_monitor_id = None
                    nove_vyskyt = []
                    search_failed = False

                    try:
                        # vytvoření dočasného monitoru pro hledání
                        temp_monitor = Monitor(
                            url=normalized_url,
                            vyrazy=json.dumps([]),  # dočasně prázdný seznam
                            email=""
                        )
                        session.add(temp_monitor)
                        session.commit()  # uložíme, aby měl ID
                        temp_monitor_id = temp_monitor.id

                        # hledání nových výskytů
                        nove_vyskyt = hledat_nove_vyskyt(temp_monitor, vyrazy_list, session)
                    except Exception:
                        session.rollback()
                        search_failed = True
                        logger.exception("Okamzite hledani web monitoru selhalo pro %s", normalized_url)
                        st.error("Hledání se nezdařilo.")
                    finally:
                        if temp_monitor_id is not None:
                            try:
                                temp_monitor = session.get(Monitor, temp_monitor_id)
                                if temp_monitor is not None:
                                    session.delete(temp_monitor)
                                    session.commit()
                            except Exception:
                                session.rollback()
                                logger.exception(
                                    "Nepodarilo se odstranit docasny monitor %s pro %s",
                                    temp_monitor_id,
                                    normalized_url,
                                )
                        session.close()

                    # zobrazení výsledků
                    if nove_vyskyt:
                        for vyraz, snippet, odkaz in nove_vyskyt:
                            if odkaz:
                                st.markdown(f'- **"{vyraz}"**: [Otevřít odkaz]({odkaz})')
                            else:
                                st.markdown(f"- **{vyraz}**: …{snippet}…")
                    elif temp_monitor_id is not None and not search_failed:
                        st.info("Žádné nové výskyty.")


    with col4:
        if st.button("Uložit monitor"):
            if not (url and vyrazy and email):
                st.warning("Vyplň všechny pole!")
            else:
                normalized_url = normalize_monitor_url(url)
                clean_email = email.strip()
                vyrazy_list = normalize_expressions(vyrazy.split(","))
                if not normalized_url:
                    st.warning("Zadej platnou URL.")
                elif not clean_email:
                    st.warning("Vyplň email.")
                elif not vyrazy_list:
                    st.warning("Zadej alespoň jeden platný výraz.")
                else:
                    session = get_session_pg()
                    monitory = session.query(Monitor).all()
                    exist_monitor = find_matching_monitor(monitory, normalized_url, clean_email)

                    if exist_monitor:
                        changed_identity = (
                            exist_monitor.url != normalized_url
                            or exist_monitor.email != clean_email
                        )
                        exist_monitor.url = normalized_url
                        exist_monitor.email = clean_email
                        exist_vyrazy = json.loads(exist_monitor.vyrazy)
                        nove_vyrazy = [v for v in vyrazy_list if v not in exist_vyrazy]
                        if not nove_vyrazy:
                            if changed_identity:
                                session.commit()
                            st.info("Tento monitor již obsahuje všechny zadané výrazy.")
                        else:
                            exist_monitor.vyrazy = json.dumps(exist_vyrazy + nove_vyrazy)
                            session.commit()
                            st.success(f"Aktualizován monitor, přidány nové výrazy: {', '.join(nove_vyrazy)}")
                    else:
                        monitor = Monitor(
                            url=normalized_url,
                            vyrazy=json.dumps(vyrazy_list),
                            email=clean_email,
                        )
                        session.add(monitor)
                        session.commit()
                        st.success("Nový monitor uložen!")
                    session.close()

    col5, col6 = st.columns(2)

    with col5:
        # -------------------------
        # Okamžité hledání
        # -------------------------
        st.markdown("---")
        st.write("📌 Okamžité hledání nových výskytů:")

    with col6:
        st.markdown("---")
        st.write("📌 Historie všech výskytů:")

        session = get_session_pg()
        results = session.query(Result).order_by(Result.datum.desc()).all()

        if results:
            for res in results:
                datum_str = res.datum.strftime("%Y-%m-%d %H:%M")
                monitor_url = res.monitor.url if res.monitor else "Nedefinovaný monitor"

                if res.odkaz:
                    st.markdown(f'- **"{res.vyraz}"** na {monitor_url} - [Otevřít odkaz]({res.odkaz}) ({datum_str})')
                elif res.snippet:
                    st.markdown(f"- **{res.vyraz}** na [{monitor_url}]({monitor_url}) ({datum_str}): …{res.snippet}…")
                else:
                    st.markdown(f"- **{res.vyraz}** na [{monitor_url}]({monitor_url}) ({datum_str})")
        else:
            st.info("Žádné záznamy v historii.")

        session.close()



    # -------------------------
    # Správa monitorů
    # -------------------------
    st.markdown("---")
    st.write("⚙️ Správa monitorů")

    session = get_session_pg()
    monitory = session.query(Monitor).order_by(Monitor.created.desc()).all()

    # Kontrola pro "refresh"
    if 'refresh' in st.session_state:
        del st.session_state['refresh']
        st.rerun()

    if not monitory:
        st.info("Žádné uložené monitory.")
    else:
        for monitor in monitory:
            with st.expander(f"🌐 {monitor.url}"):
                st.caption(f"Vytvořeno: {monitor.created.strftime('%d.%m.%Y %H:%M')}")
                form_key = f"form_{monitor.id}"
                with st.form(key=form_key):
                    col7, col8 = st.columns(2)
                    with col7:
                        # Pole pro editaci monitoru
                        new_url = st.text_input("URL", value=monitor.url, key=f"url_{monitor.id}")

                        new_vyrazy = st.text_input(
                            "Hledané výrazy (oddělené čárkou)",
                            value=", ".join(json.loads(monitor.vyrazy)),
                            key=f"vyrazy_{monitor.id}"
                        )
                    with col8:
                        new_email = st.text_input("Email", value=monitor.email, key=f"email_{monitor.id}")
                    # Layout tlačítek
                    col_save, col_delete = st.columns(2)
                    with col_save:
                        save_pressed = st.form_submit_button("💾 Uložit změny")
                        if save_pressed:
                            normalized_url = normalize_monitor_url(new_url)
                            clean_email = new_email.strip()
                            normalized_vyrazy = normalize_expressions(new_vyrazy.split(","))

                            if not normalized_url:
                                st.warning("Zadej platnou URL.")
                            elif not clean_email:
                                st.warning("Vyplň email.")
                            elif not normalized_vyrazy:
                                st.warning("Zadej alespoň jeden platný výraz.")
                            else:
                                duplicate_monitor = find_matching_monitor(
                                    monitory,
                                    normalized_url,
                                    clean_email,
                                    exclude_monitor_id=monitor.id,
                                )
                                if duplicate_monitor is not None:
                                    st.warning("Monitor pro tuto URL a email už existuje.")
                                else:
                                    monitor.url = normalized_url
                                    monitor.email = clean_email
                                    monitor.vyrazy = json.dumps(normalized_vyrazy)
                                    session.commit()
                                    st.success("Monitor upraven.")
                                    st.session_state['refresh'] = True  # trigger rerun
                                    st.rerun()

                    with col_delete:
                        confirm_delete = st.checkbox(
                            "Opravdu smazat tento monitor?", key=f"confirm_{monitor.id}"
                        )
                        delete_pressed = st.form_submit_button("🗑 Smazat monitor")
                        if delete_pressed and confirm_delete:
                            session.delete(monitor)  # cascade smaže i výsledky
                            session.commit()
                            st.warning("Monitor smazán.")
                            st.session_state['refresh'] = True  # trigger rerun
                            st.rerun()

    session.close()







