from types import SimpleNamespace

import pytest

from services.api.services.dashboard_auth import AuthorizationError, require_page_access


def test_require_page_access_allows_configurable_overview_when_assigned():
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=(),
        allowed_pages=("dashboard_overview",),
        allowed_devices=(),
    )

    require_page_access(current_user, "dashboard_overview")


def test_require_page_access_rejects_unassigned_configurable_overview():
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=(),
        allowed_pages=(),
        allowed_devices=(),
    )

    with pytest.raises(AuthorizationError):
        require_page_access(current_user, "dashboard_overview")
