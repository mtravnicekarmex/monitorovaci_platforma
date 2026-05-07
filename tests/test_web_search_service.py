import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import app.channels.email as email_module
from moduly.apps.web_search import service


class FakeField:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def in_(self, values):
        return ("in", self.name, tuple(values))


class FakeResult:
    vyraz = FakeField("vyraz")
    snippet = FakeField("snippet")
    odkaz = FakeField("odkaz")
    monitor_id = FakeField("monitor_id")

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows=None, new=None):
        self.rows = rows or []
        self.added = []
        self.new = list(new or [])
        self.flushed = False

    def query(self, *args, **kwargs):
        return FakeQuery(self.rows)

    def add(self, obj):
        self.added.append(obj)
        self.new.append(obj)

    def flush(self):
        self.flushed = True


class FakeHttpResponse:
    def __init__(self, *, text="", content=b"", headers=None):
        self.text = text
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self):
        return None


class FakeWebElement:
    def __init__(self, href, text=""):
        self.href = href
        self.text = text

    def get_attribute(self, name):
        if name == "href":
            return self.href
        return None


class FakeWebDriver:
    def __init__(self, links):
        self.links = links
        self.visited_url = None
        self.closed = False

    def get(self, url):
        self.visited_url = url

    def find_elements(self, by, value):
        assert by == "tag name"
        assert value == "a"
        return self.links

    def quit(self):
        self.closed = True


def test_normalize_expressions_filters_empty_values_and_duplicates():
    assert service.normalize_expressions([" Alpha ", "", "Beta", "Alpha", "  "]) == [
        "Alpha",
        "Beta",
    ]


def test_find_matching_monitor_uses_normalized_url_and_email_identity():
    monitors = [
        SimpleNamespace(id=1, url="example.com", email="first@example.com"),
        SimpleNamespace(id=2, url="https://example.com", email="Second@Example.com"),
    ]

    assert service.find_matching_monitor(monitors, " https://example.com ", " second@example.com ") == monitors[1]
    assert service.find_matching_monitor(monitors, "example.com", "other@example.com") is None


def test_hledat_nove_vyskyt_returns_link_and_body_hits(monkeypatch):
    body_text = ("content " * 40) + "Alpha appears in body content."
    html = f"""
    <html>
        <body>
            <a href="/docs">Alpha docs</a>
            <p>{body_text}</p>
        </body>
    </html>
    """

    monkeypatch.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(
            text=html,
            raise_for_status=lambda: None,
        ),
    )
    monkeypatch.setattr(service, "Result", FakeResult)
    monkeypatch.setattr(service, "utc_now_naive", lambda: "2026-04-02T00:00:00")

    session = FakeSession()
    monitor = SimpleNamespace(id=7, url="example.com")

    vysledky = service.hledat_nove_vyskyt(monitor, ["Alpha"], session)
    snippet_hits = [snippet for _, snippet, odkaz in vysledky if snippet and odkaz is None]

    assert ("Alpha", None, "https://example.com/docs") in vysledky
    assert any("Alpha appears in body content." in snippet for snippet in snippet_hits)
    assert all(snippet != "Alpha docs" for snippet in snippet_hits)
    assert len(session.added) == 2


def test_scan_web_hits_extracts_structured_table_rows_with_attachment_links(monkeypatch):
    html = """
    <html>
        <body>
            <div>
                <table>
                    <tr>
                        <td>Veřejné vyhlášky</td>
                        <td>06.05.2026</td>
                        <td>22.05.2026</td>
                        <td>Veřejná vyhláška - stavba "I/13 Děčín - OK Benešovská", více viz příloha.</td>
                        <td>KUUK/085742/2026</td>
                        <td>Krajský úřad Ústeckého kraje</td>
                        <td class="prilohy">
                            <a href="https://twist.mmdecin.cz/ost/xml/export.php?command=getfile&fileid=U1850233" class="ikona-souboru" title="Stáhnout přílohu"></a>
                            <a href="#" class="open-details" data-priloha_urls='["https:\\/\\/twist.mmdecin.cz\\/ost\\/xml\\/export.php?command=getfile&fileid=U1850233","https:\\/\\/twist.mmdecin.cz\\/ost\\/xml\\/export.php?command=getfile&fileid=U1850234"]' title="Informace o dokumentu"></a>
                        </td>
                    </tr>
                    <tr>
                        <td>Dražba</td>
                        <td>05.05.2026</td>
                        <td>21.05.2026</td>
                        <td>Usnesení o odročení dražebního jednání na neurčito, pov.: Michal Zvolský, více viz příloha.</td>
                        <td>043 EX 26/25 - 57</td>
                        <td>Exekutorský úřad Ostrava</td>
                        <td class="prilohy">
                            <a href="https://twist.mmdecin.cz/ost/xml/export.php?command=getfile&fileid=U1850215" class="ikona-souboru" title="Stáhnout přílohu"></a>
                        </td>
                    </tr>
                </table>
            </div>
        </body>
    </html>
    """

    monkeypatch.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(
            text=html,
            raise_for_status=lambda: None,
        ),
    )

    hits = service.scan_web_hits(
        "https://www.mmdecin.cz/uredni-deska-top",
        ["Benešovská", "I/13 Děčín", "Dražba"],
    )

    benesovska_hits = [hit for hit in hits if hit[0] == "Benešovská"]
    draza_hits = [hit for hit in hits if hit[0] == "Dražba"]

    assert benesovska_hits == [
        (
            "Benešovská",
            'Veřejné vyhlášky 06.05.2026 22.05.2026 Veřejná vyhláška - stavba "I/13 Děčín - OK Benešovská", více viz příloha. KUUK/085742/2026 Krajský úřad Ústeckého kraje',
            "https://twist.mmdecin.cz/ost/xml/export.php?command=getfile&fileid=U1850233",
        )
    ]
    assert draza_hits == [
        (
            "Dražba",
            "Dražba 05.05.2026 21.05.2026 Usnesení o odročení dražebního jednání na neurčito, pov.: Michal Zvolský, více viz příloha. 043 EX 26/25 - 57 Exekutorský úřad Ostrava",
            "https://twist.mmdecin.cz/ost/xml/export.php?command=getfile&fileid=U1850215",
        )
    ]


def test_build_pdf_attachments_collects_unique_pdf_files(monkeypatch):
    responses = {
        "https://example.com/page": FakeHttpResponse(
            text="""
            <html>
                <body>
                    <a href="/files/report.pdf">Report</a>
                    <a href="/files/report.pdf">Duplicate</a>
                    <a href="https://cdn.example.com/docs/manual.PDF">Manual</a>
                    <a href="/files/readme.txt">Readme</a>
                </body>
            </html>
            """
        ),
        "https://example.com/files/report.pdf": FakeHttpResponse(
            content=b"%PDF-report",
            headers={"Content-Type": "application/pdf"},
        ),
        "https://cdn.example.com/docs/manual.PDF": FakeHttpResponse(
            content=b"%PDF-manual",
            headers={"Content-Type": "application/pdf"},
        ),
    }

    monkeypatch.setattr(service.requests, "get", lambda url, **kwargs: responses[url])

    attachments = service.build_pdf_attachments(
        "example.com/page",
        [("Alpha", None, "https://example.com/files/report.pdf")],
    )

    assert [filename for filename, *_ in attachments] == ["report.pdf", "manual.PDF"]


def test_build_pdf_attachments_uses_attachment_marker_and_content_disposition(monkeypatch):
    responses = {
        "https://www.kr-ustecky.cz/rozhodnuti-o-povoleni-stavby-i-13-decin-ok-benesovska": FakeHttpResponse(
            text="""
            <html>
                <body>
                    <a href="/file/3385440" data-attachment-type="pdf">
                        ISSR-19794_24_SP_OK_Benesovska_Decin_Valbek_rozh2.pdf
                    </a>
                </body>
            </html>
            """
        ),
        "https://www.kr-ustecky.cz/file/3385440": FakeHttpResponse(
            content=b"%PDF-1.4 content",
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": "inline; filename=ISSR-19794_24_SP_OK_Benesovska_Decin_Valbek_rozh2.pdf",
            },
        ),
    }

    monkeypatch.setattr(service.requests, "get", lambda url, **kwargs: responses[url])

    attachments = service.build_pdf_attachments(
        "https://www.kr-ustecky.cz/rozhodnuti-o-povoleni-stavby-i-13-decin-ok-benesovska",
        [],
    )

    assert [filename for filename, *_ in attachments] == [
        "ISSR-19794_24_SP_OK_Benesovska_Decin_Valbek_rozh2.pdf"
    ]


def test_build_pdf_attachments_collects_only_matching_row_attachments(monkeypatch):
    page_url = "https://www.mmdecin.cz/uredni-deska-top"
    row_snippet = (
        'Veřejné vyhlášky 06.05.2026 22.05.2026 Veřejná vyhláška - stavba "I/13 Děčín - OK Benešovská", '
        "více viz příloha. KUUK/085742/2026 Krajský úřad Ústeckého kraje"
    )
    responses = {
        page_url: FakeHttpResponse(
            text="""
            <html>
                <body>
                    <table>
                        <tr>
                            <td>Veřejné vyhlášky</td>
                            <td>06.05.2026</td>
                            <td>22.05.2026</td>
                            <td>Veřejná vyhláška - stavba "I/13 Děčín - OK Benešovská", více viz příloha.</td>
                            <td>KUUK/085742/2026</td>
                            <td>Krajský úřad Ústeckého kraje</td>
                            <td class="prilohy">
                                <a href="https://twist.mmdecin.cz/ost/xml/export.php?command=getfile&fileid=U1850233" class="ikona-souboru" title="Stáhnout přílohu"></a>
                                <a href="https://twist.mmdecin.cz/ost/xml/export.php?command=getfile&fileid=U1850234" class="ikona-souboru" title="Stáhnout přílohu"></a>
                                <a href="#" class="zip-download" data-priloha_urls='["https:\\/\\/twist.mmdecin.cz\\/ost\\/xml\\/export.php?command=getfile&fileid=U1850233","https:\\/\\/twist.mmdecin.cz\\/ost\\/xml\\/export.php?command=getfile&fileid=U1850234"]' title="Stáhnout všechny přílohy jako ZIP"></a>
                            </td>
                        </tr>
                        <tr>
                            <td>Dražba</td>
                            <td>05.05.2026</td>
                            <td>21.05.2026</td>
                            <td>Usnesení o odročení dražebního jednání na neurčito, pov.: Michal Zvolský, více viz příloha.</td>
                            <td>043 EX 26/25 - 57</td>
                            <td>Exekutorský úřad Ostrava</td>
                            <td class="prilohy">
                                <a href="https://twist.mmdecin.cz/ost/xml/export.php?command=getfile&fileid=U1850215" class="ikona-souboru" title="Stáhnout přílohu"></a>
                            </td>
                        </tr>
                    </table>
                </body>
            </html>
            """
        ),
        "https://twist.mmdecin.cz/ost/xml/export.php?command=getfile&fileid=U1850233": FakeHttpResponse(
            content=b"%PDF-benesovska-1",
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": "attachment; filename=benesovska-1.pdf",
            },
        ),
        "https://twist.mmdecin.cz/ost/xml/export.php?command=getfile&fileid=U1850234": FakeHttpResponse(
            content=b"%PDF-benesovska-2",
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": "attachment; filename=benesovska-2.pdf",
            },
        ),
        "https://twist.mmdecin.cz/ost/xml/export.php?command=getfile&fileid=U1850215": FakeHttpResponse(
            content=b"%PDF-drazba",
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": "attachment; filename=drazba.pdf",
            },
        ),
    }

    monkeypatch.setattr(service.requests, "get", lambda url, **kwargs: responses[url])

    attachments = service.build_pdf_attachments(
        page_url,
        [
            (
                "Benešovská",
                row_snippet,
                "https://twist.mmdecin.cz/ost/xml/export.php?command=getfile&fileid=U1850233",
            )
        ],
    )

    assert [filename for filename, *_ in attachments] == ["benesovska-1.pdf", "benesovska-2.pdf"]


def test_build_pdf_attachments_scans_found_detail_pages_for_pdf(monkeypatch):
    responses = {
        "https://www.kr-ustecky.cz/ostatni-dokumenty": FakeHttpResponse(
            text="""
            <html>
                <body>
                    <a href="/rozhodnuti-o-povoleni-stavby-i-13-decin-ok-benesovska">
                        Rozhodnutí o povolení stavby
                    </a>
                </body>
            </html>
            """
        ),
        "https://www.kr-ustecky.cz/rozhodnuti-o-povoleni-stavby-i-13-decin-ok-benesovska": FakeHttpResponse(
            text="""
            <html>
                <body>
                    <a href="/file/3385440" data-attachment-type="pdf">
                        ISSR-19794_24_SP_OK_Benesovska_Decin_Valbek_rozh2.pdf
                    </a>
                </body>
            </html>
            """
        ),
        "https://www.kr-ustecky.cz/file/3385440": FakeHttpResponse(
            content=b"%PDF-1.4 content",
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": "inline; filename=ISSR-19794_24_SP_OK_Benesovska_Decin_Valbek_rozh2.pdf",
            },
        ),
    }

    monkeypatch.setattr(service.requests, "get", lambda url, **kwargs: responses[url])

    attachments = service.build_pdf_attachments(
        "https://www.kr-ustecky.cz/ostatni-dokumenty",
        [
            (
                "Rozhodnutí o povolení stavby",
                None,
                "https://www.kr-ustecky.cz/rozhodnuti-o-povoleni-stavby-i-13-decin-ok-benesovska",
            )
        ],
    )

    assert [filename for filename, *_ in attachments] == [
        "ISSR-19794_24_SP_OK_Benesovska_Decin_Valbek_rozh2.pdf"
    ]


def test_collect_pdf_urls_falls_back_to_selenium_for_dynamic_pages(monkeypatch):
    driver = FakeWebDriver([FakeWebElement("https://example.com/generated/dokument.pdf", "Dokument.pdf")])

    monkeypatch.setattr(
        service.requests,
        "get",
        lambda url, **kwargs: FakeHttpResponse(text="<html><body><span>Hi</span></body></html>"),
    )
    monkeypatch.setattr(service.webdriver, "Chrome", lambda options=None: driver)

    pdf_urls = service.collect_pdf_urls("example.com/page", [])

    assert pdf_urls == ["https://example.com/generated/dokument.pdf"]
    assert driver.visited_url == "https://example.com/page"
    assert driver.closed is True


def test_build_pdf_attachments_skips_non_pdf_payload(monkeypatch):
    responses = {
        "https://example.com/page": FakeHttpResponse(
            text='<html><body><a href="/download/report.pdf">report.pdf</a></body></html>'
        ),
        "https://example.com/download/report.pdf": FakeHttpResponse(
            content=b"<html>not a pdf</html>",
            headers={"Content-Type": "text/html"},
        ),
    }

    monkeypatch.setattr(service.requests, "get", lambda url, **kwargs: responses[url])

    attachments = service.build_pdf_attachments("example.com/page", [])

    assert attachments == []


def test_poslat_email_html_vyraz_sends_html_email_and_escapes_content(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        service,
        "build_pdf_attachments",
        lambda source_url, vyskyt_list: [("report.pdf", b"%PDF", "application", "pdf")],
    )
    monkeypatch.setattr(service, "config", lambda key: "Monitoring")
    monkeypatch.setattr(service, "send_email_outlook", lambda **kwargs: captured.update(kwargs))

    service.poslat_email_html_vyraz(
        "to@example.com",
        "Subject",
        [
            (
                "<Alert>",
                None,
                'https://example.com/doc.pdf?x=1&y=2',
            ),
            (
                "Body",
                "A&B <b>snippet</b>",
                None,
            ),
            (
                "Structured",
                "Row context",
                "https://example.com/download?id=42",
            ),
        ],
        source_url="example.com/page",
    )

    assert captured["is_html"] is True
    assert captured["attachments"] == [("report.pdf", b"%PDF", "application", "pdf")]
    assert "&lt;Alert&gt;" in captured["body"]
    assert "<strong>Body</strong>: …A&amp;B &lt;b&gt;snippet&lt;/b&gt;…" in captured["body"]
    assert "A&amp;B &lt;b&gt;snippet&lt;/b&gt;" in captured["body"]
    assert 'href="https://example.com/doc.pdf?x=1&amp;y=2"' in captured["body"]
    assert "Row context" in captured["body"]
    assert 'href="https://example.com/download?id=42"' in captured["body"]


def test_poslat_email_html_vyraz_reraises_delivery_failures(monkeypatch):
    monkeypatch.setattr(service, "build_pdf_attachments", lambda *args, **kwargs: [])
    monkeypatch.setattr(service, "config", lambda key: "Monitoring")

    def raise_delivery_error(**kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(service, "send_email_outlook", raise_delivery_error)

    with pytest.raises(RuntimeError, match="smtp down"):
        service.poslat_email_html_vyraz(
            "to@example.com",
            "Subject",
            [("Alpha", None, "https://example.com/docs")],
            source_url="example.com/page",
        )


def test_notify_new_results_for_monitor_marks_only_current_pending_results(monkeypatch):
    monitor = SimpleNamespace(id=7, email="to@example.com", url="https://example.com")
    pending_result = service.Result(
        monitor_id=7,
        url=monitor.url,
        vyraz="Alpha",
        snippet=None,
        odkaz="https://example.com/docs",
        datum=datetime.datetime(2026, 4, 9, 10, 0),
        notified=False,
    )
    older_result = service.Result(
        monitor_id=7,
        url=monitor.url,
        vyraz="Beta",
        snippet="Older hit",
        odkaz=None,
        datum=datetime.datetime(2026, 4, 9, 9, 0),
        notified=False,
    )
    session = FakeSession(new=[pending_result])
    captured = {}

    monkeypatch.setattr(
        service,
        "poslat_email_html_vyraz",
        lambda to_email, subject, vyskyt_list, source_url=None: captured.update(
            {
                "to_email": to_email,
                "subject": subject,
                "vyskyt_list": vyskyt_list,
                "source_url": source_url,
            }
        ),
    )

    notified_count = service.notify_new_results_for_monitor(
        session,
        monitor,
        [("Alpha", None, "https://example.com/docs")],
    )

    assert session.flushed is True
    assert notified_count == 1
    assert pending_result.notified is True
    assert older_result.notified is False
    assert captured["to_email"] == "to@example.com"
    assert captured["source_url"] == "https://example.com"


def test_notify_new_results_for_monitor_leaves_results_unnotified_on_email_failure(monkeypatch):
    monitor = SimpleNamespace(id=7, email="to@example.com", url="https://example.com")
    pending_result = service.Result(
        monitor_id=7,
        url=monitor.url,
        vyraz="Alpha",
        snippet=None,
        odkaz="https://example.com/docs",
        datum=datetime.datetime(2026, 4, 9, 10, 0),
        notified=False,
    )
    session = FakeSession(new=[pending_result])

    monkeypatch.setattr(
        service,
        "poslat_email_html_vyraz",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("smtp down")),
    )

    with pytest.raises(RuntimeError, match="smtp down"):
        service.notify_new_results_for_monitor(
            session,
            monitor,
            [("Alpha", None, "https://example.com/docs")],
        )

    assert session.flushed is True
    assert pending_result.notified is False


def test_send_email_outlook_builds_plain_html_and_attachment(monkeypatch):
    captured = {}

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            return None

        def starttls(self, context=None):
            return None

        def login(self, user, password):
            captured["login"] = (user, password)

        def send_message(self, msg):
            captured["message"] = msg

    monkeypatch.setattr(email_module, "config", lambda key: "x@example.com")
    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)

    email_module.send_email_outlook(
        email_receiver="to@example.com",
        subject="Subject",
        body="<h1>Hello</h1><p>World</p>",
        sender_alias="Monitoring",
        is_html=True,
        attachments=[("test.pdf", b"%PDF-1.4", "application", "pdf")],
    )

    msg = captured["message"]
    attachment_parts = list(msg.iter_attachments())

    assert msg.is_multipart() is True
    assert attachment_parts[0].get_filename() == "test.pdf"
    assert attachment_parts[0].get_content_disposition() == "attachment"
    assert any(part.get_content_type() == "text/plain" for part in msg.walk())
    assert any(part.get_content_type() == "text/html" for part in msg.walk())
