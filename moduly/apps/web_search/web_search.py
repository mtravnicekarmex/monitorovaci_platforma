import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from urllib.parse import urljoin, urlparse
import re
from datetime import datetime
from moduly.apps.web_search.database.models import Monitor, Result
from app.channels.email import send_email_outlook
from decouple import config


# -------------------------
# Funkce pro hledání nových výskytů
# -------------------------


def ensure_url_scheme(url):
    """
    Pokud URL nemá schéma (http/https), doplní https://
    """
    parsed = urlparse(url)
    if not parsed.scheme:
        return "https://" + url
    return url




def hledat_nove_vyskyt(monitor: Monitor, vyrazy: list, session):
    """
    Hledání výskytů výrazů s podporou statických i JS generovaných stránek.
    Výsledky se ukládají přes monitor_id.
    Používá předanou session (není vlastní commit).
    """
    url = ensure_url_scheme(monitor.url)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html = response.text
    except requests.RequestException as e:
        print(f"Chyba při načítání {url}: {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    text_length = len(soup.get_text(strip=True))
    is_dynamic = text_length < 200 or (not soup.find("p") and not soup.find("div"))

    if is_dynamic:
        options = Options()
        options.headless = True
        driver = webdriver.Chrome(options=options)
        try:
            driver.get(url)
            body_elem = driver.find_element("tag name", "body")
            text = body_elem.text
            links = driver.find_elements("tag name", "a")
        finally:
            driver.quit()
    else:
        text = soup.get_text(separator="\n")
        links = soup.find_all("a")

    lines = text.split("\n")
    link_texts = [a.text if is_dynamic else a.get_text() for a in links]

    nove_vyskyt = []

    for vyraz in vyrazy:
        pattern = re.compile(re.escape(vyraz), re.IGNORECASE)
        in_link = any(pattern.search(lt) for lt in link_texts)

        if in_link:
            for a in links:
                a_text = a.text if is_dynamic else a.get_text()
                if pattern.search(a_text):
                    href = a.get_attribute('href') if is_dynamic else a.get('href')
                    odkaz = urljoin(url, href) if href else url

                    exists = session.query(Result).filter_by(
                        monitor_id=monitor.id,
                        vyraz=vyraz,
                        odkaz=odkaz
                    ).first()

                    if not exists:
                        result = Result(
                            monitor_id=monitor.id,
                            url=url,
                            vyraz=vyraz,
                            snippet=None,
                            odkaz=odkaz,
                            datum=datetime.now(),
                            notified=False
                        )
                        session.add(result)
                        nove_vyskyt.append((vyraz, None, odkaz))

        else:
            for line in lines:
                if pattern.search(line):
                    snippet = line.strip()

                    exists = session.query(Result).filter_by(
                        monitor_id=monitor.id,
                        vyraz=vyraz,
                        snippet=snippet
                    ).first()

                    if not exists:
                        result = Result(
                            monitor_id=monitor.id,
                            url=url,
                            vyraz=vyraz,
                            snippet=snippet,
                            odkaz=None,
                            datum=datetime.now(),
                            notified=False
                        )
                        session.add(result)
                        nove_vyskyt.append((vyraz, snippet, None))

    return nove_vyskyt



# -------------------------
# Funkce pro HTML email
# -------------------------
def poslat_email_html_vyraz(to_email, subject, vyskyt_list):
    if not vyskyt_list:
        return
    html_content = "<h2>Nové výskyty na sledovaných stránkách</h2><ul>"
    for vyraz, snippet, odkaz in vyskyt_list:
        if odkaz:
            html_content += f"<li><strong>{vyraz}:</strong> <a href='{odkaz}' target='_blank'>{odkaz}</a></li>"
        else:
            html_content += f"<li><strong>{vyraz}</strong>: …{snippet}…</li>"
    html_content += "</ul>"

    try:
        send_email_outlook(email_receiver=to_email, subject=subject, body=html_content, sender_alias=config('O_EMAIL_UPOZORNENI'))
        print(f"HTML email odeslán na {to_email}")
    except Exception as e:
        print(f"Chyba při odesílání emailu: {e}")

























#
# # -------------------------
# # Streamlit UI
# # -------------------------
# st.set_page_config(
#     page_title = 'Monitor webových stránek',
#     page_icon = '🔍',
#     layout="wide")
#
#
# with st.container():
#     st.subheader("Monitor webových stránek")
#     st.write("Upozornění na nové výskyty hledaných výrazů z vybraných webových stránek jsou odesílána e‑mailem každý den v 6:00 a 14:00.")
#
#     col1, col2 = st.columns(2)
#
#     with col1:
#         url = st.text_input("Zadat URL")
#         vyrazy = st.text_input("Hledané výrazy (oddělené čárkou)")
#
#
#
#     with col2:
#         # frequency = st.selectbox("Frekvence reportu", ["denně", "týdně", "měsíčně"])
#         email = st.text_input("Email pro zasílání upozornění")
#
#
#
#
#     col3, col4 = st.columns(2)
#     with col3:
#         if st.button("Hledat nyní"):
#             if not url or not vyrazy:
#                 st.warning("Zadej URL a hledané výrazy!")
#             else:
#                 session = get_session_pg()
#
#                 # vytvoření dočasného monitoru pro hledání
#                 temp_monitor = Monitor(
#                     url=url,
#                     vyrazy=json.dumps([]),  # dočasně prázdný seznam
#                     email=""
#                 )
#                 session.add(temp_monitor)
#                 session.commit()  # uložíme, aby měl ID
#
#                 # seznam hledaných výrazů
#                 vyrazy_list = [v.strip() for v in vyrazy.split(",")]
#
#                 # hledání nových výskytů
#                 nove_vyskyt = hledat_nove_vyskyt(temp_monitor, vyrazy_list)
#
#                 # smažeme dočasný monitor
#                 session.delete(temp_monitor)
#                 session.commit()
#                 session.close()
#
#                 # zobrazení výsledků
#                 if not nove_vyskyt:
#                     st.info("Žádné nové výskyty.")
#                 else:
#                     for vyraz, snippet, odkaz in nove_vyskyt:
#                         if odkaz:
#                             st.markdown(f'- **"{vyraz}"**: [Otevřít odkaz]({odkaz})')
#                         else:
#                             st.markdown(f"- **{vyraz}**: …{snippet}…")
#
#
#     with col4:
#         if st.button("Uložit monitor"):
#             if not (url and vyrazy and email):
#                 st.warning("Vyplň všechny pole!")
#             else:
#                 session = get_session_pg()
#                 vyrazy_list = [v.strip() for v in vyrazy.split(",")]
#                 exist_monitor = session.query(Monitor).filter_by(url=url).first()
#
#                 if exist_monitor:
#                     exist_vyrazy = json.loads(exist_monitor.vyrazy)
#                     nove_vyrazy = [v for v in vyrazy_list if v not in exist_vyrazy]
#                     if not nove_vyrazy:
#                         st.info("Tento monitor již obsahuje všechny zadané výrazy.")
#                     else:
#                         exist_monitor.vyrazy = json.dumps(exist_vyrazy + nove_vyrazy)
#                         exist_monitor.email = email
#                         session.commit()
#                         st.success(f"Aktualizován monitor, přidány nové výrazy: {', '.join(nove_vyrazy)}")
#                 else:
#                     monitor = Monitor(url=url, vyrazy=json.dumps(vyrazy_list), email=email)
#                     session.add(monitor)
#                     session.commit()
#                     st.success("Nový monitor uložen!")
#                 session.close()
#
#     col5, col6 = st.columns(2)
#
#     with col5:
#         # -------------------------
#         # Okamžité hledání
#         # -------------------------
#         st.markdown("---")
#         st.write("📌 Okamžité hledání nových výskytů:")
#
#     with col6:
#         st.markdown("---")
#         st.write("📌 Historie všech výskytů:")
#
#         session = get_session_pg()
#         results = session.query(Result).order_by(Result.datum.desc()).all()
#
#         if results:
#             for res in results:
#                 datum_str = res.datum.strftime("%Y-%m-%d %H:%M")
#                 monitor_url = res.monitor.url if res.monitor else "Nedefinovaný monitor"
#
#                 if res.odkaz:
#                     st.markdown(f'- **"{res.vyraz}"** na {monitor_url} - [Otevřít odkaz]({res.odkaz}) ({datum_str})')
#                 elif res.snippet:
#                     st.markdown(f"- **{res.vyraz}** na [{monitor_url}]({monitor_url}) ({datum_str}): …{res.snippet}…")
#                 else:
#                     st.markdown(f"- **{res.vyraz}** na [{monitor_url}]({monitor_url}) ({datum_str})")
#         else:
#             st.info("Žádné záznamy v historii.")
#
#         session.close()
#
#
#
#     # -------------------------
#     # Správa monitorů
#     # -------------------------
#     st.markdown("---")
#     st.write("⚙️ Správa monitorů")
#
#     session = get_session_pg()
#     monitory = session.query(Monitor).order_by(Monitor.created.desc()).all()
#
#     # Kontrola pro "refresh"
#     if 'refresh' in st.session_state:
#         del st.session_state['refresh']
#         st.rerun()
#
#     if not monitory:
#         st.info("Žádné uložené monitory.")
#     else:
#         for monitor in monitory:
#             with st.expander(f"🌐 {monitor.url}"):
#                 st.caption(f"Vytvořeno: {monitor.created.strftime('%d.%m.%Y %H:%M')}")
#                 form_key = f"form_{monitor.id}"
#                 with st.form(key=form_key):
#                     col7, col8 = st.columns(2)
#                     with col7:
#                         # Pole pro editaci monitoru
#                         new_url = st.text_input("URL", value=monitor.url, key=f"url_{monitor.id}")
#
#                         new_vyrazy = st.text_input(
#                             "Hledané výrazy (oddělené čárkou)",
#                             value=", ".join(json.loads(monitor.vyrazy)),
#                             key=f"vyrazy_{monitor.id}"
#                         )
#                     with col8:
#                         new_email = st.text_input("Email", value=monitor.email, key=f"email_{monitor.id}")
#                     # Layout tlačítek
#                     col_save, col_delete = st.columns(2)
#                     with col_save:
#                         save_pressed = st.form_submit_button("💾 Uložit změny")
#                         if save_pressed:
#                             monitor.url = new_url.strip()
#                             monitor.email = new_email.strip()
#                             monitor.vyrazy = json.dumps(
#                                 [v.strip() for v in new_vyrazy.split(",") if v.strip()]
#                             )
#                             session.commit()
#                             st.success("Monitor upraven.")
#                             st.session_state['refresh'] = True  # trigger rerun
#
#                     with col_delete:
#                         confirm_delete = st.checkbox(
#                             "Opravdu smazat tento monitor?", key=f"confirm_{monitor.id}"
#                         )
#                         delete_pressed = st.form_submit_button("🗑 Smazat monitor")
#                         if delete_pressed and confirm_delete:
#                             session.delete(monitor)  # cascade smaže i výsledky
#                             session.commit()
#                             st.warning("Monitor smazán.")
#                             st.session_state['refresh'] = True  # trigger rerun
#
#     session.close()
#





