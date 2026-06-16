from pathlib import Path
import re
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version
import pytest

from scripts import run_with_rotating_log
from scripts import verify_production_environment


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_LAUNCHERS = (
    PROJECT_ROOT / "start_api_dashboard.bat",
    PROJECT_ROOT / "scripts" / "start_api.ps1",
    PROJECT_ROOT / "scripts" / "start_all_services.ps1",
)
DEVELOPMENT_LAUNCHERS = (
    PROJECT_ROOT / "scripts" / "start_api_dev.ps1",
    PROJECT_ROOT / "scripts" / "start_all_services_dev.ps1",
)


def _load_exact_requirements(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        specifiers = list(requirement.specifier)
        assert requirement.url is None
        assert requirement.marker is None
        assert len(specifiers) == 1
        assert specifiers[0].operator == "=="
        name = canonicalize_name(requirement.name)
        assert name not in pins
        pins[name] = specifiers[0].version
    return pins


def test_production_launchers_use_locked_environment_without_reload():
    for path in PRODUCTION_LAUNCHERS:
        source = path.read_text(encoding="utf-8")

        assert ".venv-production" in source
        assert "verify_production_environment.py" in source
        assert "--reload" not in source

    batch_source = PRODUCTION_LAUNCHERS[0].read_text(encoding="utf-8")
    assert "--host 127.0.0.1 --port 8000 --workers 1" in batch_source
    assert "--server.address 127.0.0.1 --server.port 8001" in batch_source
    assert "--log-name api" in batch_source
    assert "--log-name dashboard" in batch_source
    assert "--log-name caddy" in batch_source
    assert "0.0.0.0" not in batch_source
    assert "cmd /c" in batch_source
    assert "cmd /k" not in batch_source
    assert re.search(r"(?im)^\s*pause\s*$", batch_source) is None


def test_development_reload_is_confined_to_explicit_dev_launchers():
    for path in DEVELOPMENT_LAUNCHERS:
        source = path.read_text(encoding="utf-8")

        assert ".venv\\Scripts\\python.exe" in source
        assert "--reload" in source
        assert "127.0.0.1" in source


def test_legacy_launcher_copy_only_delegates_to_production_launcher():
    source = (
        PROJECT_ROOT / "start_api_dashboard - kopie.bat"
    ).read_text(encoding="utf-8")

    assert "start_api_dashboard.bat" in source
    assert "uvicorn" not in source
    assert "streamlit" not in source


def test_production_direct_requirements_are_stable_and_present_in_lock():
    direct = _load_exact_requirements(PROJECT_ROOT / "requirements-production.in")
    locked = _load_exact_requirements(
        PROJECT_ROOT / "requirements-production.lock.txt"
    )

    assert len(direct) >= 20
    assert len(locked) >= 70
    for name, version in direct.items():
        assert locked[name] == version
        assert not Version(version).is_prerelease
    assert all(not Version(version).is_prerelease for version in locked.values())


def test_requirements_api_delegates_to_production_lock():
    source = (PROJECT_ROOT / "requirements-api.txt").read_text(encoding="utf-8")

    assert source.splitlines()[-1] == "-r requirements-production.lock.txt"


def test_lock_parser_rejects_duplicate_canonical_names(tmp_path):
    lock_path = tmp_path / "lock.txt"
    lock_path.write_text("Example_Package==1.0\nexample-package==1.0\n")

    with pytest.raises(ValueError, match="Duplicate lock entry"):
        verify_production_environment.load_locked_versions(lock_path)


def test_runtime_log_wrapper_records_output_and_exit(tmp_path):
    log_path = tmp_path / "service.log"

    return_code = run_with_rotating_log.run_logged_process(
        [sys.executable, "-c", "print('runtime-check')"],
        log_path=log_path,
        max_bytes=1024,
        backup_count=2,
    )

    source = log_path.read_text(encoding="utf-8")
    assert return_code == 0
    assert "process_start executable=" in source
    assert "runtime-check" in source
    assert "process_exit code=0" in source


def test_runtime_log_wrapper_rotates_and_limits_backups(tmp_path):
    log_path = tmp_path / "service.log"

    return_code = run_with_rotating_log.run_logged_process(
        [sys.executable, "-c", "print('x' * 200)"],
        log_path=log_path,
        max_bytes=100,
        backup_count=2,
    )

    assert return_code == 0
    assert log_path.is_file()
    assert (tmp_path / "service.log.1").is_file()
    assert not (tmp_path / "service.log.3").exists()
