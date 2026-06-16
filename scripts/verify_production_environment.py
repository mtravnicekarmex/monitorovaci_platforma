from __future__ import annotations

from importlib import metadata
from pathlib import Path
import re
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = PROJECT_ROOT / "requirements-production.lock.txt"
EXPECTED_PYTHON = (3, 14)
EXPECTED_PIP = "26.1.2"
ALLOWED_UNLOCKED_PACKAGES = {"pip"}
PIN_PATTERN = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s;]+)$")


def _canonicalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def load_locked_versions(path: Path = LOCK_PATH) -> dict[str, tuple[str, str]]:
    locked: dict[str, tuple[str, str]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_PATTERN.fullmatch(line)
        if match is None:
            raise ValueError(f"Unsupported lock entry: {line}")
        name = match.group("name")
        canonical_name = _canonicalize_name(name)
        if canonical_name in locked:
            raise ValueError(f"Duplicate lock entry: {name}")
        locked[canonical_name] = (name, match.group("version"))
    return locked


def verify_environment() -> list[str]:
    errors: list[str] = []
    locked = load_locked_versions()
    if sys.version_info[:2] != EXPECTED_PYTHON:
        errors.append(
            "Python version mismatch: "
            f"expected {EXPECTED_PYTHON[0]}.{EXPECTED_PYTHON[1]}, "
            f"found {sys.version_info.major}.{sys.version_info.minor}"
        )

    try:
        installed_pip = metadata.version("pip")
    except metadata.PackageNotFoundError:
        errors.append(f"Missing package: pip=={EXPECTED_PIP}")
    else:
        if installed_pip != EXPECTED_PIP:
            errors.append(
                f"Version mismatch for pip: expected {EXPECTED_PIP}, "
                f"found {installed_pip}"
            )

    installed_names = {
        _canonicalize_name(distribution.metadata["Name"])
        for distribution in metadata.distributions()
        if distribution.metadata["Name"]
    }
    unlocked = installed_names - set(locked) - ALLOWED_UNLOCKED_PACKAGES
    for canonical_name in sorted(unlocked):
        errors.append(f"Unlocked package installed: {canonical_name}")

    for canonical_name, (name, expected_version) in locked.items():
        try:
            installed_version = metadata.version(name)
        except metadata.PackageNotFoundError:
            errors.append(f"Missing package: {name}=={expected_version}")
            continue
        if installed_version != expected_version:
            errors.append(
                f"Version mismatch for {canonical_name}: "
                f"expected {expected_version}, found {installed_version}"
            )
    return errors


def main() -> int:
    errors = verify_environment()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Production Python environment matches requirements-production.lock.txt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
