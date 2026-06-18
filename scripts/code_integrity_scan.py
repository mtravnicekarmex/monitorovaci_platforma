from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_VERSION = 1
DEFAULT_TASK_NAME = "MonitoringCodeIntegrityScan"
DEFAULT_EXCLUDES = (
    ".git/**",
    ".venv/**",
    ".venv-production/**",
    "**/__pycache__/**",
    "**/*.pyc",
    "core/scheduler/locks/**",
    "core/scheduler/logs/**",
    "core/scheduler/data/**",
    "data/**",
    "moduly/mereni/elektromery/data/**",
    "frontend_next/tsconfig.tsbuildinfo",
    "*.lnk",
)
UNTRACKED_SOURCE_SUFFIXES = {
    ".bat",
    ".cmd",
    ".config",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".php",
    ".ps1",
    ".py",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
UNTRACKED_SOURCE_NAMES = {
    ".env.example",
    "AGENTS.md",
    "Caddyfile",
    "DECISIONS.md",
    "DASHBOARD_SECURITY_CHECKLIST.md",
    "requirements-api.txt",
    "requirements-production.in",
    "requirements-production.lock.txt",
    "SESSION_NOTES.md",
    "start_api_dashboard.bat",
}


@dataclass(frozen=True)
class FileRecord:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ScanResult:
    status: str
    missing: tuple[str, ...]
    changed: tuple[str, ...]
    unexpected: tuple[str, ...]
    scanned_count: int
    report_path: Path | None


def _program_data_root() -> Path:
    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        return Path(program_data) / "monitorovaci_platforma"
    return PROJECT_ROOT / ".codex" / "local_programdata"


def default_manifest_path() -> Path:
    return _program_data_root() / "security" / "code_integrity_manifest.json"


def default_report_dir() -> Path:
    return _program_data_root() / "logs" / "security"


def _run_git(project_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout


def _to_relative_posix(project_root: Path, path: Path | str) -> str:
    if isinstance(path, Path):
        relative = path.relative_to(project_root)
        parts = relative.parts
    else:
        parts = PurePosixPath(path.replace("\\", "/")).parts
    return "/".join(part for part in parts if part not in ("", "."))


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns)


def is_excluded_path(path: str) -> bool:
    return _matches_any(path, DEFAULT_EXCLUDES)


def is_untracked_source_path(path: str) -> bool:
    if is_excluded_path(path):
        return False
    normalized = path.replace("\\", "/")
    name = PurePosixPath(normalized).name
    if name in UNTRACKED_SOURCE_NAMES:
        return True
    return PurePosixPath(normalized).suffix.lower() in UNTRACKED_SOURCE_SUFFIXES


def list_tracked_paths(project_root: Path) -> tuple[str, ...]:
    output = _run_git(project_root, "ls-files", "-z")
    paths = [
        item.replace("\\", "/")
        for item in output.split("\0")
        if item
    ]
    return tuple(sorted(path for path in paths if not is_excluded_path(path)))


def list_untracked_source_paths(project_root: Path) -> tuple[str, ...]:
    output = _run_git(
        project_root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )
    paths = [
        item.replace("\\", "/")
        for item in output.split("\0")
        if item
    ]
    return tuple(sorted(path for path in paths if is_untracked_source_path(path)))


def list_dirty_scanned_paths(project_root: Path) -> tuple[str, ...]:
    output = _run_git(project_root, "status", "--porcelain", "-z", "--untracked-files=all")
    dirty: set[str] = set()
    chunks = [chunk for chunk in output.split("\0") if chunk]
    index = 0
    while index < len(chunks):
        entry = chunks[index]
        status = entry[:2]
        path_text = entry[3:] if len(entry) > 3 else ""
        if status.startswith("R") or status.startswith("C"):
            index += 1
            if index < len(chunks):
                path_text = chunks[index]
        if path_text:
            path = path_text.replace("\\", "/")
            if not is_excluded_path(path):
                if status == "??":
                    if is_untracked_source_path(path):
                        dirty.add(path)
                else:
                    dirty.add(path)
        index += 1
    return tuple(sorted(dirty))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_records(project_root: Path, paths: Iterable[str]) -> dict[str, FileRecord]:
    records: dict[str, FileRecord] = {}
    for relative_path in sorted(paths):
        absolute_path = project_root / PurePosixPath(relative_path)
        if not absolute_path.is_file():
            continue
        stat = absolute_path.stat()
        records[relative_path] = FileRecord(
            path=relative_path,
            sha256=sha256_file(absolute_path),
            size=stat.st_size,
        )
    return records


def build_manifest(project_root: Path) -> dict[str, object]:
    paths = list_tracked_paths(project_root)
    records = build_records(project_root, paths)
    head = _run_git(project_root, "rev-parse", "HEAD").strip()
    generated_at = datetime.now(timezone.utc).isoformat()
    return {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": generated_at,
        "generated_from_head": head,
        "project_root": str(project_root),
        "scope": {
            "tracked_files": True,
            "excluded_patterns": list(DEFAULT_EXCLUDES),
            "unexpected_untracked_source_files": True,
        },
        "files": {
            path: {"sha256": record.sha256, "size": record.size}
            for path, record in records.items()
        },
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_manifest(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError(f"Unsupported manifest version in {path}")
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"Manifest does not contain a valid file map: {path}")
    return payload


def compare_manifest(
    project_root: Path,
    manifest: dict[str, object],
    *,
    report_dir: Path | None = None,
) -> ScanResult:
    expected_files = manifest["files"]
    assert isinstance(expected_files, dict)

    current_records = build_records(project_root, expected_files.keys())
    missing = tuple(
        sorted(path for path in expected_files if path not in current_records)
    )
    changed: list[str] = []
    for path, raw_expected in expected_files.items():
        if path not in current_records or not isinstance(raw_expected, dict):
            continue
        expected_sha = raw_expected.get("sha256")
        if current_records[path].sha256 != expected_sha:
            changed.append(path)

    unexpected = list_untracked_source_paths(project_root)
    status = "ok" if not missing and not changed and not unexpected else "drift"
    report_path = None
    if report_dir is not None:
        report_path = write_report(
            report_dir,
            {
                "status": status,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "project_root": str(project_root),
                "manifest_head": manifest.get("generated_from_head"),
                "manifest_generated_at": manifest.get("generated_at"),
                "scanned_count": len(expected_files),
                "missing": list(missing),
                "changed": sorted(changed),
                "unexpected": list(unexpected),
            },
        )

    return ScanResult(
        status=status,
        missing=missing,
        changed=tuple(sorted(changed)),
        unexpected=unexpected,
        scanned_count=len(expected_files),
        report_path=report_path,
    )


def write_report(report_dir: Path, payload: dict[str, object]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = report_dir / f"code_integrity_report_{timestamp}.json"
    write_json(report_path, payload)
    write_json(report_dir / "code_integrity_latest.json", payload)
    return report_path


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root to scan.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=default_manifest_path(),
        help="Manifest path. Defaults to ProgramData security storage.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=default_report_dir(),
        help="Directory for scan reports.",
    )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or verify the approved code integrity manifest."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    baseline = subparsers.add_parser(
        "baseline",
        help="Write a new approved manifest for tracked code and configuration files.",
    )
    _add_common_arguments(baseline)
    baseline.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow creating a baseline while scanned files are modified.",
    )

    scan = subparsers.add_parser(
        "scan",
        help="Compare the repository against the approved manifest.",
    )
    _add_common_arguments(scan)
    return parser


def command_baseline(args: argparse.Namespace) -> int:
    project_root = args.project_root.resolve()
    dirty_paths = list_dirty_scanned_paths(project_root)
    if dirty_paths and not args.allow_dirty:
        print(
            "Refusing to create a baseline while scanned files are dirty. "
            "Review or commit the changes first, or pass --allow-dirty after approval.",
            file=sys.stderr,
        )
        for path in dirty_paths[:50]:
            print(f"dirty: {path}", file=sys.stderr)
        if len(dirty_paths) > 50:
            print(f"dirty: ... {len(dirty_paths) - 50} more", file=sys.stderr)
        return 1

    manifest = build_manifest(project_root)
    write_json(args.manifest, manifest)
    file_count = len(manifest["files"])
    print(f"Wrote code integrity baseline: {args.manifest} ({file_count} files)")
    if dirty_paths:
        print(f"Baseline included {len(dirty_paths)} dirty scanned path(s).")
    return 0


def command_scan(args: argparse.Namespace) -> int:
    project_root = args.project_root.resolve()
    if not args.manifest.is_file():
        print(f"Code integrity manifest is missing: {args.manifest}", file=sys.stderr)
        return 1

    try:
        manifest = load_manifest(args.manifest)
        result = compare_manifest(project_root, manifest, report_dir=args.report_dir)
    except Exception as exc:
        print(f"Code integrity scan failed: {exc}", file=sys.stderr)
        return 1

    report_text = f" report={result.report_path}" if result.report_path else ""
    if result.status == "ok":
        print(f"Code integrity scan OK: {result.scanned_count} files.{report_text}")
        return 0

    print(
        "Code integrity drift detected: "
        f"changed={len(result.changed)} missing={len(result.missing)} "
        f"unexpected={len(result.unexpected)}.{report_text}",
        file=sys.stderr,
    )
    for label, paths in (
        ("changed", result.changed),
        ("missing", result.missing),
        ("unexpected", result.unexpected),
    ):
        for path in paths[:50]:
            print(f"{label}: {path}", file=sys.stderr)
        if len(paths) > 50:
            print(f"{label}: ... {len(paths) - 50} more", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    if args.command == "baseline":
        return command_baseline(args)
    if args.command == "scan":
        return command_scan(args)
    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
