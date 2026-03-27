from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from decouple import config
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from sqlalchemy.orm import Session

from app.channels.email import send_email_outlook
from app.time_utils import utc_now_naive
from moduly.apps.web_search.database.models import Monitor, Result


logger = logging.getLogger(__name__)


def ensure_url_scheme(url: str) -> str:
    """Add https:// when the URL is missing a scheme."""
    parsed = urlparse(url)
    if not parsed.scheme:
        return "https://" + url
    return url


def hledat_nove_vyskyt(
    monitor: Monitor,
    vyrazy: list[str],
    session: Session,
) -> list[tuple[str, str | None, str | None]]:
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
    except requests.RequestException as exc:
        logger.warning("Chyba pri nacitani %s: %s", url, exc)
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

    existing_rows = (
        session.query(Result.vyraz, Result.snippet, Result.odkaz)
        .filter(
            Result.monitor_id == monitor.id,
            Result.vyraz.in_(vyrazy),
        )
        .all()
    )
    existing_link_hits = {
        (row.vyraz, row.odkaz) for row in existing_rows if row.odkaz
    }
    existing_snippet_hits = {
        (row.vyraz, row.snippet) for row in existing_rows if row.snippet
    }

    for vyraz in vyrazy:
        pattern = re.compile(re.escape(vyraz), re.IGNORECASE)
        in_link = any(pattern.search(link_text) for link_text in link_texts)

        if in_link:
            for link in links:
                link_text = link.text if is_dynamic else link.get_text()
                if pattern.search(link_text):
                    href = link.get_attribute("href") if is_dynamic else link.get("href")
                    odkaz = urljoin(url, href) if href else url
                    key = (vyraz, odkaz)

                    if key not in existing_link_hits:
                        result = Result(
                            monitor_id=monitor.id,
                            url=url,
                            vyraz=vyraz,
                            snippet=None,
                            odkaz=odkaz,
                            datum=utc_now_naive(),
                            notified=False,
                        )
                        session.add(result)
                        nove_vyskyt.append((vyraz, None, odkaz))
                        existing_link_hits.add(key)
        else:
            for line in lines:
                if pattern.search(line):
                    snippet = line.strip()
                    key = (vyraz, snippet)

                    if key not in existing_snippet_hits:
                        result = Result(
                            monitor_id=monitor.id,
                            url=url,
                            vyraz=vyraz,
                            snippet=snippet,
                            odkaz=None,
                            datum=utc_now_naive(),
                            notified=False,
                        )
                        session.add(result)
                        nove_vyskyt.append((vyraz, snippet, None))
                        existing_snippet_hits.add(key)

    return nove_vyskyt


def poslat_email_html_vyraz(
    to_email: str,
    subject: str,
    vyskyt_list: list[tuple[str, str | None, str | None]],
) -> None:
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
        send_email_outlook(
            email_receiver=to_email,
            subject=subject,
            body=html_content,
            sender_alias=config("O_EMAIL_UPOZORNENI"),
        )
        logger.info("HTML email odeslan na %s", to_email)
    except Exception as exc:
        logger.exception("Chyba pri odesilani emailu na %s: %s", to_email, exc)
