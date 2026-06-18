from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

from scripts import code_integrity_scan


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


def test_scan_detects_changed_missing_and_unexpected_source_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (repo / "requirements-production.lock.txt").write_text(
        "example==1.0\n",
        encoding="utf-8",
    )
    (repo / "data").mkdir()
    (repo / "data" / "session_cookies.json").write_text("{}", encoding="utf-8")
    _commit_all(repo)

    manifest = code_integrity_scan.build_manifest(repo)

    (repo / "app.py").write_text("print('changed')\n", encoding="utf-8")
    (repo / "requirements-production.lock.txt").unlink()
    (repo / "unexpected.py").write_text("print('new')\n", encoding="utf-8")
    (repo / "data" / "runtime.py").write_text("print('ignored')\n", encoding="utf-8")

    result = code_integrity_scan.compare_manifest(repo, manifest)

    assert result.status == "drift"
    assert result.changed == ("app.py",)
    assert result.missing == ("requirements-production.lock.txt",)
    assert result.unexpected == ("unexpected.py",)
    assert result.scanned_count == 2


def test_baseline_dirty_check_ignores_runtime_data_but_not_code(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (repo / "data").mkdir()
    (repo / "data" / "session_cookies.json").write_text("{}", encoding="utf-8")
    _commit_all(repo)

    (repo / "app.py").write_text("print('changed')\n", encoding="utf-8")
    (repo / "data" / "session_cookies.json").write_text(
        '{"changed": true}',
        encoding="utf-8",
    )

    assert code_integrity_scan.list_dirty_scanned_paths(repo) == ("app.py",)


def test_sensitive_and_runtime_paths_are_excluded_from_integrity_scope():
    excluded_paths = (
        "data/smartfuelpass/session_cookies.json",
        "data/smartfuelpass/auto_login_session.json",
        "core/scheduler/locks/daily_job.lock",
        "core/scheduler/logs/scheduler.log",
        "core/scheduler/data/database_availability.sqlite3",
        "moduly/mereni/elektromery/data/old/19891.ts",
        "frontend_next/tsconfig.tsbuildinfo",
    )

    for path in excluded_paths:
        assert code_integrity_scan.is_excluded_path(path)
        assert not code_integrity_scan.is_untracked_source_path(path)


def test_integrity_scan_scripts_are_scheduled_task_entrypoints():
    runner = (PROJECT_ROOT / "scripts" / "run_code_integrity_scan.ps1").read_text(
        encoding="utf-8"
    )
    registrar = (
        PROJECT_ROOT / "scripts" / "register_code_integrity_scan_task.ps1"
    ).read_text(encoding="utf-8")

    assert ".venv-production\\Scripts\\python.exe" in runner
    assert "code_integrity_scan.py" in runner
    assert "Baseline" in runner
    assert "Scan" in runner
    assert "Register-ScheduledTask" in registrar
    assert "MonitoringCodeIntegrityScan" in registrar
    assert "run_code_integrity_scan.ps1" in registrar
