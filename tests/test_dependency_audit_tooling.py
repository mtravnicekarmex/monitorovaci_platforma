from pathlib import Path

from packaging.requirements import Requirement


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        names.add(Requirement(line).name.lower().replace("_", "-"))
    return names


def test_security_toolchain_is_separate_from_production_runtime():
    production_lock = _requirement_names(
        PROJECT_ROOT / "requirements-production.lock.txt"
    )
    security_direct = _requirement_names(PROJECT_ROOT / "requirements-security.in")

    assert "pip-audit" in security_direct
    assert "pip-audit" not in production_lock

    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".venv-security/" in gitignore


def test_security_bootstrap_uses_security_venv_and_lock():
    source = (
        PROJECT_ROOT / "scripts" / "bootstrap_security_toolchain.ps1"
    ).read_text(encoding="utf-8")

    assert ".venv-security" in source
    assert "requirements-security.lock.txt" in source
    assert "pip_audit --version" in source
    assert ".venv-production" not in source


def test_dependency_audit_runner_checks_lock_and_environment():
    source = (PROJECT_ROOT / "scripts" / "run_dependency_audit.ps1").read_text(
        encoding="utf-8"
    )

    assert ".venv-security" in source
    assert ".venv-production" in source
    assert "verify_production_environment.py" in source
    assert "requirements-production.lock.txt" in source
    assert "--no-deps" in source
    assert "--path" in source
    assert "dependency_audit_latest.json" in source
    assert "pip install" not in source.lower()


def test_dependency_audit_has_scheduled_task_entrypoint():
    source = (
        PROJECT_ROOT / "scripts" / "register_dependency_audit_task.ps1"
    ).read_text(encoding="utf-8")

    assert "Register-ScheduledTask" in source
    assert "MonitoringDependencyAudit" in source
    assert "run_dependency_audit.ps1" in source
    assert "InteractiveToken" not in source
    assert "-LogonType Interactive" in source
    assert "LeastPrivilege" not in source
    assert "-RunLevel Limited" in source
    assert "-At $time" in source
    assert "-At $time.TimeOfDay" not in source
