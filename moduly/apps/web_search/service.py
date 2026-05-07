from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
import logging
import re
from collections.abc import Iterable
from urllib.parse import unquote, urljoin, urlparse

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
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
MAX_PDF_ATTACHMENTS = 5
MAX_PDF_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_SOURCE_PAGES = 5
PDF_MAGIC = b"%PDF"


@dataclass(frozen=True)
class SearchLinkEntry:
    text: str
    href: str | None
    snippet: str | None = None


def ensure_url_scheme(url: str) -> str:
    """Add https:// when the URL is missing a scheme."""
    parsed = urlparse(url)
    if not parsed.scheme:
        return "https://" + url
    return url


def normalize_monitor_url(url: str) -> str:
    """Trim whitespace and ensure a scheme for monitor URLs."""
    cleaned = url.strip()
    if not cleaned:
        return ""
    return ensure_url_scheme(cleaned)


def normalize_monitor_email(email: str) -> str:
    """Normalize email for identity comparisons."""
    return email.strip().casefold()


def find_matching_monitor(
    monitory: Iterable[Monitor],
    url: str,
    email: str,
    exclude_monitor_id: int | None = None,
) -> Monitor | None:
    """Find monitor with the same normalized URL and email."""
    normalized_url = normalize_monitor_url(url)
    normalized_email = normalize_monitor_email(email)

    for monitor in monitory:
        if exclude_monitor_id is not None and monitor.id == exclude_monitor_id:
            continue
        if (
            normalize_monitor_url(monitor.url) == normalized_url
            and normalize_monitor_email(monitor.email) == normalized_email
        ):
            return monitor

    return None


def normalize_expressions(vyrazy: Iterable[str]) -> list[str]:
    """Strip whitespace, drop empty values and keep only the first occurrence."""
    normalized: list[str] = []
    seen: set[str] = set()

    for vyraz in vyrazy:
        cleaned = vyraz.strip()
        if not cleaned or cleaned in seen:
            continue
        normalized.append(cleaned)
        seen.add(cleaned)

    return normalized


def is_pdf_url(url: str) -> bool:
    """Return True when the URL path points to a PDF file."""
    return urlparse(url).path.lower().endswith(".pdf")


def looks_like_pdf_reference(url: str | None, link_text: str | None = None) -> bool:
    """Return True when the URL or link label looks like it points to a PDF."""
    if not url:
        return False

    parsed = urlparse(url)
    haystacks = [
        url.lower(),
        parsed.path.lower(),
        parsed.query.lower(),
        (link_text or "").lower(),
    ]
    return any(".pdf" in haystack for haystack in haystacks)


def has_pdf_attachment_marker(marker: str | None) -> bool:
    """Return True when a site explicitly marks an attachment as PDF."""
    return (marker or "").strip().casefold() == "pdf"


def looks_like_download_reference(
    url: str | None,
    link_text: str | None = None,
    title: str | None = None,
) -> bool:
    """Return True when the URL or metadata looks like a direct file download."""
    if not url:
        return False

    parsed = urlparse(url)
    haystacks = [
        url.lower(),
        parsed.path.lower(),
        parsed.query.lower(),
        (link_text or "").lower(),
        (title or "").lower(),
    ]
    keywords = (
        "/file/",
        "download",
        "getfile",
        "stahni",
        "stáhnout",
        "priloha",
        "příloha",
        "attachment",
        "id_priloha",
        "fileid=",
        "export.php",
    )
    return any(keyword in haystack for haystack in haystacks for keyword in keywords)


def normalize_match_text(text: str | None) -> str:
    """Normalize text for fuzzy row matching."""
    return re.sub(r"\s+", " ", (text or "")).strip().casefold()


def parse_attachment_url_list(raw_urls: str | None) -> list[str]:
    """Parse JSON-like attachment URL lists from HTML attributes."""
    if not raw_urls:
        return []

    candidates = [raw_urls]
    cleaned = raw_urls.replace("&quot;", '"')
    if cleaned != raw_urls:
        candidates.append(cleaned)

    for candidate in candidates:
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, list):
            return [str(item) for item in decoded if item]

    return []


def extract_attachment_urls_from_element(element: BeautifulSoup, page_url: str) -> list[str]:
    """Extract direct attachment URLs from an element and its descendants."""
    attachment_urls: list[str] = []
    seen: set[str] = set()

    def add_attachment_url(candidate: str | None) -> None:
        if not candidate:
            return
        normalized_candidate = ensure_url_scheme(urljoin(page_url, candidate.strip()))
        if normalized_candidate in seen:
            return
        seen.add(normalized_candidate)
        attachment_urls.append(normalized_candidate)

    for tag in [element, *element.find_all(True)]:
        raw_urls = tag.get("data-priloha_urls")
        for candidate in parse_attachment_url_list(raw_urls):
            add_attachment_url(candidate)

        if tag.name != "a":
            continue

        href = tag.get("href")
        link_text = tag.get_text(" ", strip=True)
        title = tag.get("title")
        attachment_type = tag.get("data-attachment-type")
        classes = set(tag.get("class", []))
        if href and href != "#" and (
            has_pdf_attachment_marker(attachment_type)
            or looks_like_pdf_reference(href, link_text)
            or looks_like_download_reference(href, link_text, title)
            or "ikona-souboru" in classes
        ):
            add_attachment_url(href)

    return attachment_urls


def extract_structured_row_entries(soup: BeautifulSoup, page_url: str) -> list[SearchLinkEntry]:
    """Build synthetic link entries for table-like rows with attachment icons."""
    entries: list[SearchLinkEntry] = []
    seen: set[tuple[str, str]] = set()

    for row in soup.find_all("tr"):
        row_text = row.get_text(" ", strip=True)
        attachment_urls = extract_attachment_urls_from_element(row, page_url)
        if not row_text or not attachment_urls:
            continue

        key = (row_text, attachment_urls[0])
        if key in seen:
            continue

        entries.append(
            SearchLinkEntry(
                text=row_text,
                href=attachment_urls[0],
                snippet=row_text,
            )
        )
        seen.add(key)

    return entries


def row_relates_to_hit(row_text: str, vyraz: str, snippet: str | None) -> bool:
    """Return True when a table row likely belongs to a found hit."""
    normalized_row = normalize_match_text(row_text)
    normalized_vyraz = normalize_match_text(vyraz)
    normalized_snippet = normalize_match_text(snippet)

    if normalized_snippet and (
        normalized_snippet in normalized_row or normalized_row in normalized_snippet
    ):
        return True
    return bool(normalized_vyraz and normalized_vyraz in normalized_row)


def extract_contextual_attachment_urls(
    soup: BeautifulSoup,
    page_url: str,
    vyskyt_list: Iterable[tuple[str, str | None, str | None]],
) -> list[str]:
    """Collect attachment URLs only from rows that match current hits."""
    contextual_urls: list[str] = []
    seen: set[str] = set()

    def add_attachment_url(candidate: str) -> None:
        if candidate in seen:
            return
        seen.add(candidate)
        contextual_urls.append(candidate)

    for row in soup.find_all("tr"):
        row_text = row.get_text(" ", strip=True)
        if not row_text:
            continue
        if not any(row_relates_to_hit(row_text, vyraz, snippet) for vyraz, snippet, _ in vyskyt_list):
            continue
        for candidate in extract_attachment_urls_from_element(row, page_url):
            add_attachment_url(candidate)

    return contextual_urls


def extract_filename_from_response(response: requests.Response, fallback_url: str, index: int) -> str:
    """Prefer filename from Content-Disposition, otherwise derive it from URL."""
    content_disposition = response.headers.get("Content-Disposition", "")

    utf8_match = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition, flags=re.IGNORECASE)
    if utf8_match:
        filename = unquote(utf8_match.group(1).strip().strip('"'))
    else:
        filename_match = re.search(r'filename="?([^";]+)"?', content_disposition, flags=re.IGNORECASE)
        if filename_match:
            filename = filename_match.group(1).strip()
        else:
            filename = unquote(urlparse(fallback_url).path.rsplit("/", 1)[-1]) or f"priloha_{index}.pdf"

    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    return filename


def collect_pdf_urls(
    source_url: str | None,
    vyskyt_list: Iterable[tuple[str, str | None, str | None]],
) -> list[str]:
    """Collect unique PDF URLs from the page itself and from found links."""
    pdf_urls: list[str] = []
    seen: set[str] = set()

    def add_pdf_url(
        candidate: str | None,
        link_text: str | None = None,
        attachment_type: str | None = None,
        title: str | None = None,
        allow_download: bool = False,
    ) -> None:
        if not candidate:
            return
        normalized_candidate = ensure_url_scheme(candidate.strip())
        if (
            has_pdf_attachment_marker(attachment_type)
            or looks_like_pdf_reference(normalized_candidate, link_text)
            or (allow_download and looks_like_download_reference(normalized_candidate, link_text, title))
        ) and normalized_candidate not in seen:
            seen.add(normalized_candidate)
            pdf_urls.append(normalized_candidate)

    for _, _, odkaz in vyskyt_list:
        add_pdf_url(odkaz, allow_download=True)

    pages_to_scan: list[str] = []
    queued_pages: set[str] = set()

    def queue_page(candidate: str | None) -> None:
        if not candidate:
            return
        normalized_candidate = normalize_monitor_url(candidate)
        if (
            not normalized_candidate
            or is_pdf_url(normalized_candidate)
            or looks_like_download_reference(normalized_candidate)
            or normalized_candidate in queued_pages
        ):
            return
        queued_pages.add(normalized_candidate)
        pages_to_scan.append(normalized_candidate)

    queue_page(source_url)
    for _, _, odkaz in vyskyt_list:
        queue_page(odkaz)

    for page_url in pages_to_scan[:MAX_PDF_SOURCE_PAGES]:
        try:
            response = requests.get(page_url, headers=REQUEST_HEADERS, timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Chyba pri nacitani stranky pro PDF prilohy %s: %s", page_url, exc)
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        contextual_attachment_urls = extract_contextual_attachment_urls(soup, page_url, vyskyt_list)
        if contextual_attachment_urls:
            for attachment_url in contextual_attachment_urls:
                add_pdf_url(attachment_url, allow_download=True)
            continue

        for anchor in soup.find_all("a", href=True):
            add_pdf_url(
                urljoin(page_url, anchor["href"]),
                anchor.get_text(" ", strip=True),
                anchor.get("data-attachment-type"),
                anchor.get("title"),
                allow_download=True,
            )

        text_length = len(soup.get_text(strip=True))
        is_dynamic = text_length < 200 or (not soup.find("p") and not soup.find("div"))
        if not is_dynamic:
            continue

        options = Options()
        options.headless = True
        driver = None
        try:
            driver = webdriver.Chrome(options=options)
            driver.get(page_url)
            for link in driver.find_elements("tag name", "a"):
                add_pdf_url(
                    link.get_attribute("href"),
                    link.text,
                    link.get_attribute("data-attachment-type"),
                    link.get_attribute("title"),
                    allow_download=True,
                )
        except Exception as exc:
            logger.warning("Chyba pri renderovani stranky pro PDF prilohy %s: %s", page_url, exc)
        finally:
            if driver is not None:
                driver.quit()

    return pdf_urls


def build_pdf_attachments(
    source_url: str | None,
    vyskyt_list: Iterable[tuple[str, str | None, str | None]],
) -> list[tuple[str, bytes, str, str]]:
    """Download PDF files referenced from the monitored page and found links."""
    attachments: list[tuple[str, bytes, str, str]] = []
    total_size = 0

    for pdf_url in collect_pdf_urls(source_url, vyskyt_list):
        if len(attachments) >= MAX_PDF_ATTACHMENTS:
            logger.info("Preskakuji dalsi PDF prilohy pro %s: dosazen limit %s", source_url, MAX_PDF_ATTACHMENTS)
            break

        try:
            response = requests.get(pdf_url, headers=REQUEST_HEADERS, timeout=20)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Chyba pri stahovani PDF prilohy %s: %s", pdf_url, exc)
            continue

        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if content_type and content_type != "application/pdf" and not is_pdf_url(pdf_url):
            logger.warning("Preskakuji nepriznanou PDF prilohu %s s content-type %s", pdf_url, content_type)
            continue

        content = response.content
        if not content:
            logger.warning("PDF priloha %s je prazdna", pdf_url)
            continue
        if content_type != "application/pdf" and not content.startswith(PDF_MAGIC):
            logger.warning(
                "Preskakuji prilohu %s, protoze stazeny obsah nevypada jako PDF",
                pdf_url,
            )
            continue
        if len(content) > MAX_PDF_ATTACHMENT_BYTES:
            logger.warning(
                "PDF priloha %s presahuje limit %s bajtu",
                pdf_url,
                MAX_PDF_ATTACHMENT_BYTES,
            )
            continue
        if total_size + len(content) > MAX_TOTAL_PDF_BYTES:
            logger.warning(
                "PDF priloha %s by prekrocila celkovy limit %s bajtu",
                pdf_url,
                MAX_TOTAL_PDF_BYTES,
            )
            continue

        filename = extract_filename_from_response(response, pdf_url, len(attachments) + 1)

        attachments.append((filename, content, "application", "pdf"))
        total_size += len(content)

    logger.info(
        "Pripraveno %s PDF priloh pro %s: %s",
        len(attachments),
        source_url,
        ", ".join(filename for filename, *_ in attachments) if attachments else "-",
    )
    return attachments


def _load_search_page(url: str) -> tuple[list[SearchLinkEntry], list[str]]:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=10)
    response.raise_for_status()
    html = response.text

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
            link_entries = [
                SearchLinkEntry(
                    text=link.text,
                    href=link.get_attribute("href"),
                )
                for link in driver.find_elements("tag name", "a")
            ]
        finally:
            driver.quit()

        link_text_set = {entry.text.strip() for entry in link_entries if entry.text and entry.text.strip()}
        lines = [
            line.strip()
            for line in text.split("\n")
            if line.strip() and line.strip() not in link_text_set
        ]
        return link_entries, lines

    link_entries = [
        SearchLinkEntry(
            text=anchor.get_text(" ", strip=True),
            href=anchor.get("href"),
        )
        for anchor in soup.find_all("a")
        if anchor.get_text(" ", strip=True)
    ]
    link_entries.extend(extract_structured_row_entries(soup, url))
    text_soup = BeautifulSoup(html, "html.parser")
    for anchor in text_soup.find_all("a"):
        anchor.decompose()
    text = text_soup.get_text(separator="\n")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return link_entries, lines


def scan_web_hits(
    url: str,
    vyrazy: Iterable[str],
) -> list[tuple[str, str | None, str | None]]:
    normalized_vyrazy = normalize_expressions(vyrazy)
    if not normalized_vyrazy:
        return []

    normalized_url = ensure_url_scheme(url)
    try:
        link_entries, lines = _load_search_page(normalized_url)
    except requests.RequestException as exc:
        logger.warning("Chyba pri nacitani %s: %s", normalized_url, exc)
        return []

    hits: list[tuple[str, str | None, str | None]] = []
    seen_link_hits: set[tuple[str, str]] = set()
    seen_snippet_hits: set[tuple[str, str]] = set()
    linked_snippet_hits: set[tuple[str, str]] = set()

    for vyraz in normalized_vyrazy:
        pattern = re.compile(re.escape(vyraz), re.IGNORECASE)

        for link_entry in link_entries:
            if not pattern.search(link_entry.text or ""):
                continue
            odkaz = urljoin(normalized_url, link_entry.href) if link_entry.href else normalized_url
            key = (vyraz, odkaz)
            if key in seen_link_hits:
                continue
            hits.append((vyraz, link_entry.snippet, odkaz))
            seen_link_hits.add(key)
            if link_entry.snippet:
                linked_snippet_hits.add((vyraz, normalize_match_text(link_entry.snippet)))

        for line in lines:
            if not pattern.search(line):
                continue
            snippet = line.strip()
            normalized_snippet = normalize_match_text(snippet)
            if any(
                existing_vyraz == vyraz
                and (
                    normalized_snippet in linked_snippet
                    or linked_snippet in normalized_snippet
                )
                for existing_vyraz, linked_snippet in linked_snippet_hits
            ):
                continue
            key = (vyraz, snippet)
            if key in seen_snippet_hits:
                continue
            hits.append((vyraz, snippet, None))
            seen_snippet_hits.add(key)

    return hits


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
    vyrazy = normalize_expressions(vyrazy)
    if not vyrazy:
        return []

    url = ensure_url_scheme(monitor.url)
    candidate_hits = scan_web_hits(url, vyrazy)
    if not candidate_hits:
        return []

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

    nove_vyskyt = []
    for vyraz, snippet, odkaz in candidate_hits:
        if odkaz:
            key = (vyraz, odkaz)
            if key in existing_link_hits:
                continue
            result = Result(
                monitor_id=monitor.id,
                url=url,
                vyraz=vyraz,
                snippet=snippet,
                odkaz=odkaz,
                datum=utc_now_naive(),
                notified=False,
            )
            session.add(result)
            nove_vyskyt.append((vyraz, snippet, odkaz))
            existing_link_hits.add(key)
            continue

        if not snippet:
            continue
        key = (vyraz, snippet)
        if key in existing_snippet_hits:
            continue
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


def notify_new_results_for_monitor(
    session: Session,
    monitor: Monitor,
    vyskyt_list: list[tuple[str, str | None, str | None]],
) -> int:
    if not vyskyt_list:
        return 0

    new_results = [
        obj
        for obj in session.new
        if isinstance(obj, Result) and getattr(obj, "monitor_id", None) == monitor.id
    ]
    if not new_results:
        return 0

    session.flush()
    poslat_email_html_vyraz(
        monitor.email,
        f"Nový výskyt na {monitor.url}",
        vyskyt_list,
        source_url=monitor.url,
    )
    for result in new_results:
        result.notified = True

    return len(new_results)


def poslat_email_html_vyraz(
    to_email: str,
    subject: str,
    vyskyt_list: list[tuple[str, str | None, str | None]],
    source_url: str | None = None,
) -> None:
    if not vyskyt_list:
        return

    attachments = build_pdf_attachments(source_url, vyskyt_list)

    html_parts = ["<h2>Nové výskyty na sledovaných stránkách</h2>", "<ul>"]
    for vyraz, snippet, odkaz in vyskyt_list:
        safe_vyraz = escape(vyraz)
        if odkaz and snippet:
            safe_odkaz = escape(odkaz, quote=True)
            safe_snippet = escape(snippet)
            html_parts.append(
                f'<li><strong>{safe_vyraz}</strong>: …{safe_snippet}… '
                f'(<a href="{safe_odkaz}" target="_blank" rel="noopener noreferrer">{safe_odkaz}</a>)</li>'
            )
        elif odkaz:
            safe_odkaz = escape(odkaz, quote=True)
            html_parts.append(
                f'<li><strong>{safe_vyraz}:</strong> '
                f'<a href="{safe_odkaz}" target="_blank" rel="noopener noreferrer">{safe_odkaz}</a></li>'
            )
        else:
            safe_snippet = escape(snippet or "")
            html_parts.append(f"<li><strong>{safe_vyraz}</strong>: …{safe_snippet}…</li>")
    html_parts.append("</ul>")

    if attachments:
        attachment_names = ", ".join(escape(filename) for filename, *_ in attachments)
        html_parts.append(f"<p>Přiložené PDF soubory: {attachment_names}</p>")

    html_content = "".join(html_parts)

    try:
        send_email_outlook(
            email_receiver=to_email,
            subject=subject,
            body=html_content,
            is_html=True,
            sender_alias=config("O_EMAIL_UPOZORNENI"),
            attachments=attachments,
        )
        logger.info("HTML email odeslan na %s", to_email)
    except Exception as exc:
        logger.exception("Chyba pri odesilani emailu na %s: %s", to_email, exc)
        raise
