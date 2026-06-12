from pathlib import Path
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


def test_runtime_launchers_do_not_contain_or_assign_api_token_secret():
    for launcher_path in RUNTIME_LAUNCHERS:
        source = launcher_path.read_text(encoding="utf-8")

        assert COMPROMISED_DEVELOPMENT_SECRET.decode("ascii") not in source
        assert "API_TOKEN_SECRET=" not in source


def test_compromised_development_secret_is_absent_from_tracked_files():
    output = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=PROJECT_ROOT,
    )
    tracked_paths = [
        PROJECT_ROOT / raw_path.decode("utf-8")
        for raw_path in output.split(b"\0")
        if raw_path
    ]

    matching_paths = [
        path.relative_to(PROJECT_ROOT)
        for path in tracked_paths
        if path.is_file() and COMPROMISED_DEVELOPMENT_SECRET in path.read_bytes()
    ]

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
