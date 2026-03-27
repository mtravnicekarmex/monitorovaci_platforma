import json

import streamlit as st

from core.db.connect import get_session_pg
from moduly.apps.web_search.database.models import Monitor, Result
from moduly.apps.web_search.service import hledat_nove_vyskyt





























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
                session = get_session_pg()

                # vytvoření dočasného monitoru pro hledání
                temp_monitor = Monitor(
                    url=url,
                    vyrazy=json.dumps([]),  # dočasně prázdný seznam
                    email=""
                )
                session.add(temp_monitor)
                session.commit()  # uložíme, aby měl ID

                # seznam hledaných výrazů
                vyrazy_list = [v.strip() for v in vyrazy.split(",")]

                # hledání nových výskytů
                nove_vyskyt = hledat_nove_vyskyt(temp_monitor, vyrazy_list, session)

                # smažeme dočasný monitor
                session.delete(temp_monitor)
                session.commit()
                session.close()

                # zobrazení výsledků
                if not nove_vyskyt:
                    st.info("Žádné nové výskyty.")
                else:
                    for vyraz, snippet, odkaz in nove_vyskyt:
                        if odkaz:
                            st.markdown(f'- **"{vyraz}"**: [Otevřít odkaz]({odkaz})')
                        else:
                            st.markdown(f"- **{vyraz}**: …{snippet}…")


    with col4:
        if st.button("Uložit monitor"):
            if not (url and vyrazy and email):
                st.warning("Vyplň všechny pole!")
            else:
                session = get_session_pg()
                vyrazy_list = [v.strip() for v in vyrazy.split(",")]
                exist_monitor = session.query(Monitor).filter_by(url=url).first()

                if exist_monitor:
                    exist_vyrazy = json.loads(exist_monitor.vyrazy)
                    nove_vyrazy = [v for v in vyrazy_list if v not in exist_vyrazy]
                    if not nove_vyrazy:
                        st.info("Tento monitor již obsahuje všechny zadané výrazy.")
                    else:
                        exist_monitor.vyrazy = json.dumps(exist_vyrazy + nove_vyrazy)
                        exist_monitor.email = email
                        session.commit()
                        st.success(f"Aktualizován monitor, přidány nové výrazy: {', '.join(nove_vyrazy)}")
                else:
                    monitor = Monitor(url=url, vyrazy=json.dumps(vyrazy_list), email=email)
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
                            monitor.url = new_url.strip()
                            monitor.email = new_email.strip()
                            monitor.vyrazy = json.dumps(
                                [v.strip() for v in new_vyrazy.split(",") if v.strip()]
                            )
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







