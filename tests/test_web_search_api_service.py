from types import SimpleNamespace

import pytest

from services.api.services.dashboard_auth import AuthorizationError
from services.api.services import web_search as web_search_service


def test_preview_hits_admin_normalizes_inputs_and_returns_hits(monkeypatch):
    current_user = SimpleNamespace(is_admin=True)
    captured = {}

    def fake_scan(url, expressions):
        captured["url"] = url
        captured["expressions"] = list(expressions)
        return [("Alpha", None, "https://example.com/docs")]

    monkeypatch.setattr(web_search_service, "scan_web_hits", fake_scan)

    preview = web_search_service.preview_hits_admin(
        current_user,
        url=" example.com ",
        expressions=[" Alpha ", "", "Alpha"],
    )

    assert captured["url"] == "https://example.com"
    assert captured["expressions"] == ["Alpha"]
    assert preview["url"] == "https://example.com"
    assert preview["total"] == 1
    assert preview["hits"] == [{"vyraz": "Alpha", "snippet": None, "odkaz": "https://example.com/docs"}]


def test_preview_hits_admin_requires_web_search_page_access():
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=(),
        allowed_pages=(),
        allowed_devices=(),
    )

    with pytest.raises(AuthorizationError):
        web_search_service.preview_hits_admin(
            current_user,
            url="example.com",
            expressions=["Alpha"],
        )


def test_preview_hits_admin_allows_user_with_web_search_page(monkeypatch):
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=("sprava",),
        allowed_pages=("web_search_monitor",),
        allowed_devices=(),
    )
    monkeypatch.setattr(web_search_service, "scan_web_hits", lambda *_: [])

    preview = web_search_service.preview_hits_admin(
        current_user,
        url="example.com",
        expressions=["Alpha"],
    )

    assert preview["url"] == "https://example.com"
    assert preview["total"] == 0
