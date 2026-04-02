import sys
from pathlib import Path
from types import SimpleNamespace

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
    def __init__(self, rows=None):
        self.rows = rows or []
        self.added = []

    def query(self, *args, **kwargs):
        return FakeQuery(self.rows)

    def add(self, obj):
        self.added.append(obj)


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
        ],
        source_url="example.com/page",
    )

    assert captured["is_html"] is True
    assert captured["attachments"] == [("report.pdf", b"%PDF", "application", "pdf")]
    assert "&lt;Alert&gt;" in captured["body"]
    assert "<strong>Body</strong>: …A&amp;B &lt;b&gt;snippet&lt;/b&gt;…" in captured["body"]
    assert "A&amp;B &lt;b&gt;snippet&lt;/b&gt;" in captured["body"]
    assert 'href="https://example.com/doc.pdf?x=1&amp;y=2"' in captured["body"]


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
