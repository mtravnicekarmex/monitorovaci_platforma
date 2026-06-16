import base64
import hashlib
from pathlib import Path
import re
import subprocess

import pytest

from services.api.core import config as api_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_LAUNCHERS = (
    PROJECT_ROOT / "start_api_dashboard.bat",
    PROJECT_ROOT / "start_api_dashboard - kopie.bat",
    PROJECT_ROOT / "scripts" / "start_all_services.ps1",
    PROJECT_ROOT / "run.txt",
)
COMPROMISED_DEVELOPMENT_SECRET = b"monitoring-platforma-" + b"local-dev-secret"
DASHBOARD_SOURCE_ROOT = PROJECT_ROOT / "moduly" / "apps" / "dashboard"
LEAFLET_ASSET_ROOT = DASHBOARD_SOURCE_ROOT / "assets" / "leaflet" / "1.9.4"
LEAFLET_SRI_SHA256 = {
    "leaflet.css": "p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=",
    "leaflet.js": "20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=",
}
EXTERNAL_SCRIPT_PATTERN = re.compile(
    r"""<script\b[^>]*\bsrc\s*=\s*["']https?://""",
    flags=re.IGNORECASE,
)


def test_runtime_launchers_do_not_contain_or_assign_api_token_secret():
    for launcher_path in RUNTIME_LAUNCHERS:
        source = launcher_path.read_text(encoding="utf-8")

        assert COMPROMISED_DEVELOPMENT_SECRET.decode("ascii") not in source
        assert "API_TOKEN_SECRET=" not in source


def test_compromised_development_secret_is_absent_from_tracked_files():
    result = subprocess.run(
        [
            "git",
            "grep",
            "--cached",
            "-l",
            "-F",
            COMPROMISED_DEVELOPMENT_SECRET.decode("ascii"),
            "--",
            ".",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == b""


def test_vendored_leaflet_assets_match_reviewed_release_hashes():
    for asset_name, expected_hash in LEAFLET_SRI_SHA256.items():
        digest = hashlib.sha256((LEAFLET_ASSET_ROOT / asset_name).read_bytes()).digest()
        assert base64.b64encode(digest).decode("ascii") == expected_hash

    assert (LEAFLET_ASSET_ROOT / "LICENSE").is_file()


def test_active_dashboard_sources_do_not_load_external_executable_scripts():
    matching_paths = []
    for pattern in ("*.py", "*.html"):
        for path in DASHBOARD_SOURCE_ROOT.rglob(pattern):
            source = path.read_text(encoding="utf-8")
            if EXTERNAL_SCRIPT_PATTERN.search(source):
                matching_paths.append(path.relative_to(PROJECT_ROOT))

    assert matching_paths == []


@pytest.mark.parametrize("configured_value", ["", "change-me", " CHANGE-ME "])
def test_api_startup_rejects_missing_or_placeholder_token_secret(
    monkeypatch,
    configured_value,
):
    monkeypatch.setattr(
        api_config,
        "config",
        lambda _name, default="": configured_value,
    )

    with pytest.raises(ValueError, match="API_TOKEN_SECRET"):
        api_config._get_required_token_secret()


@pytest.mark.parametrize(
    ("absolute_minutes", "inactivity_minutes", "message"),
    [
        (480, 0, "API_SESSION_INACTIVITY_MINUTES"),
        (30, 31, "nesmi byt vyssi"),
    ],
)
def test_api_startup_rejects_invalid_session_timeouts(
    monkeypatch,
    absolute_minutes,
    inactivity_minutes,
    message,
):
    values = {
        "API_TITLE": "Test API",
        "API_VERSION": "test",
        "API_TOKEN_EXPIRY_MINUTES": absolute_minutes,
        "API_SESSION_INACTIVITY_MINUTES": inactivity_minutes,
    }

    def fake_config(name, default=None, cast=None):
        value = values.get(name, default)
        return cast(value) if cast is not None else value

    monkeypatch.setattr(api_config, "config", fake_config)
    monkeypatch.setattr(
        api_config,
        "_get_required_token_secret",
        lambda: "test-secret",
    )
    monkeypatch.setattr(api_config, "_get_cors_origins", lambda: ())

    with pytest.raises(ValueError, match=message):
        api_config.get_api_settings()


def test_api_docs_are_disabled_by_default(monkeypatch):
    values = {
        "API_TITLE": "Test API",
        "API_VERSION": "test",
        "API_TOKEN_EXPIRY_MINUTES": 480,
        "API_SESSION_INACTIVITY_MINUTES": 30,
    }

    def fake_config(name, default=None, cast=None):
        value = values.get(name, default)
        return cast(value) if cast is not None else value

    monkeypatch.setattr(api_config, "config", fake_config)
    monkeypatch.setattr(
        api_config,
        "_get_required_token_secret",
        lambda: "test-secret",
    )
    monkeypatch.setattr(api_config, "_get_cors_origins", lambda: ())

    assert api_config.get_api_settings().enable_docs is False


def test_api_docs_can_be_enabled_explicitly(monkeypatch):
    values = {
        "API_TITLE": "Test API",
        "API_VERSION": "test",
        "API_TOKEN_EXPIRY_MINUTES": 480,
        "API_SESSION_INACTIVITY_MINUTES": 30,
        "API_ENABLE_DOCS": "true",
    }

    def fake_config(name, default=None, cast=None):
        value = values.get(name, default)
        return cast(value) if cast is not None else value

    monkeypatch.setattr(api_config, "config", fake_config)
    monkeypatch.setattr(
        api_config,
        "_get_required_token_secret",
        lambda: "test-secret",
    )
    monkeypatch.setattr(api_config, "_get_cors_origins", lambda: ())

    assert api_config.get_api_settings().enable_docs is True
