from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

from scripts import secret_hygiene_scan


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(repo: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git executable is not available")
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "security-test@example.invalid")
    _run_git(repo, "config", "user.name", "Security Test")


def _commit_all(repo: Path) -> None:
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "baseline")


def test_report_redacts_current_and_history_secret_values(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    secret_value = "super-secret-value-12345"
    (repo / "start.bat").write_text(
        f"set API_TOKEN_SECRET={secret_value}\n",
        encoding="utf-8",
    )
    _commit_all(repo)
    (repo / "start.bat").write_text("echo cleaned\n", encoding="utf-8")
    _commit_all(repo)

    report = secret_hygiene_scan.build_report(repo, include_history=True)
    encoded = str(report)

    assert report["status"] == "findings"
    assert "hardcoded_api_token_secret" in encoded
    assert secret_value not in encoded
    assert "REDACTED" in encoded


def test_sensitive_session_paths_are_flagged_without_content_scan(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    session_path = repo / "data" / "smartfuelpass"
    session_path.mkdir(parents=True)
    (session_path / "session_cookies.json").write_text(
        '{"cookie": "live-session-cookie-123456789"}',
        encoding="utf-8",
    )
    _commit_all(repo)

    report = secret_hygiene_scan.build_report(repo, include_history=False)
    encoded = str(report)

    assert "smartfuelpass_session_cookie_file" in encoded
    assert "live-session-cookie" not in encoded


def test_project_gitignore_covers_known_generated_secret_and_artifact_paths():
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    expected_patterns = (
        ".env",
        ".env.*",
        "data/smartfuelpass/session_cookies.json",
        "data/smartfuelpass/auto_login_session.json",
        "moduly/mereni/elektromery/SOFTLINK/lds_auth.json",
        "core/scheduler/locks/*.lock",
        "frontend_next/tsconfig.tsbuildinfo",
        "moduly/mereni/elektromery/data/**/*.ts",
        "moduly/mereni/elektromery/data/**/*.xlsx",
    )

    for pattern in expected_patterns:
        assert pattern in gitignore
