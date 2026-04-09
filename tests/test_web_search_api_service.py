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


def test_preview_hits_admin_requires_admin():
    current_user = SimpleNamespace(is_admin=False)

    with pytest.raises(AuthorizationError):
        web_search_service.preview_hits_admin(
            current_user,
            url="example.com",
            expressions=["Alpha"],
        )
