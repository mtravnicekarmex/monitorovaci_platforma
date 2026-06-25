from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import fnmatch
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 1_000_000
MAX_HISTORY_MATCHES_PER_COMMIT = 200
TEXT_SOURCE_SUFFIXES = {
    ".bat",
    ".cmd",
    ".config",
    ".css",
    ".env",
    ".html",
    ".in",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
TEXT_SOURCE_NAMES = {
    ".env",
    ".env.example",
    ".gitattributes",
    ".gitignore",
    "Caddyfile",
    "run.txt",
}
CODE_SUFFIXES = {".js", ".py", ".ts", ".tsx"}

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "private_key_block",
        re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
        "critical",
    ),
    (
        "hardcoded_api_token_secret",
        re.compile(
            r"(?i)\bAPI_TOKEN_SECRET\b\s*(?:=|:)\s*['\"]?[A-Za-z0-9_.:/+=@-]{16,}"
        ),
        "critical",
    ),
    (
        "credential_literal",
        re.compile(
            r"(?i)\b(password|passwd|pwd|api[_-]?key|secret[_-]?key|"
            r"client[_-]?secret|access[_-]?token|refresh[_-]?token|"
            r"session[_-]?token|session[_-]?cookie)\b\s*(?:=|:)\s*"
            r"['\"][^'\"\s]{8,}['\"]"
        ),
        "high",
    ),
    (
        "authorization_bearer_literal",
        re.compile(r"(?i)\bAuthorization\b\s*(?:=|:)\s*['\"]Bearer\s+[^'\"]{8,}['\"]"),
        "high",
    ),
    (
        "url_embedded_credentials",
        re.compile(r"(?i)://[^/\s:@]+:[^/\s@]+@"),
        "high",
    ),
    (
        "connection_string_password",
        re.compile(r"(?i)\b(?:password|pwd)\s*=\s*[^;\s]{4,}"),
        "high",
    ),
)

SENSITIVE_PATH_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("data/smartfuelpass/session_cookies.json", "smartfuelpass_session_cookie_file", "critical"),
    ("data/smartfuelpass/auto_login_session.json", "smartfuelpass_auto_login_file", "critical"),
    ("**/.env", "environment_secret_file", "critical"),
    (".env", "environment_secret_file", "critical"),
    (".env.*", "environment_secret_file", "critical"),
    ("**/lds_auth.json", "softlink_auth_file", "critical"),
    ("**/*credentials*.json", "credential_named_file", "high"),
    ("**/*credentials*.txt", "credential_named_file", "high"),
    ("**/*secret*.json", "secret_named_file", "high"),
    ("**/*secret*.txt", "secret_named_file", "high"),
)

OPERATIONAL_ARTIFACT_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("core/scheduler/locks/*.lock", "tracked_scheduler_lock", "medium"),
    ("frontend_next/tsconfig.tsbuildinfo", "tracked_build_artifact", "medium"),
    ("moduly/mereni/elektromery/data/**", "tracked_meter_source_data", "high"),
)

PLACEHOLDER_MARKERS = (
    "changeme",
    "change-me",
    "example",
    "placeholder",
    "dummy",
    "test",
    "not-recorded",
    "your-",
)
SAFE_TEMPLATE_PATHS = {
    ".env.example",
    "frontend_next/.env.example",
}
CONTENT_SCAN_EXCLUDED_PATTERNS = (
    "tests/**",
    "scripts/secret_hygiene_scan.py",
)


@dataclass(frozen=True)
class Finding:
    scope: str
    rule: str
    severity: str
    path: str
    line: int | None = None
    commit: str | None = None
    note: str | None = None

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "scope": self.scope,
            "rule": self.rule,
            "severity": self.severity,
            "path": self.path,
        }
        if self.line is not None:
            payload["line"] = self.line
        if self.commit is not None:
            payload["commit"] = self.commit
        if self.note:
            payload["note"] = self.note
        payload["value"] = "REDACTED"
        return payload


def _run_git(project_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=project_root,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _split_z(output: str) -> tuple[str, ...]:
    return tuple(item for item in output.split("\0") if item)


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def _matches(pattern: str, path: str) -> bool:
    return fnmatch.fnmatchcase(_normalize_path(path), pattern)


def _is_safe_template_path(path: str) -> bool:
    return _normalize_path(path) in SAFE_TEMPLATE_PATHS


def _is_content_scan_excluded(path: str) -> bool:
    normalized = _normalize_path(path)
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in CONTENT_SCAN_EXCLUDED_PATTERNS)


def _match_path_rules(path: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    if _is_safe_template_path(path):
        return matches
    for pattern, rule, severity in SENSITIVE_PATH_PATTERNS:
        if _matches(pattern, path):
            matches.append((rule, severity))
    for pattern, rule, severity in OPERATIONAL_ARTIFACT_PATTERNS:
        if _matches(pattern, path):
            matches.append((rule, severity))
    return matches


def _is_sensitive_path(path: str) -> bool:
    if _is_safe_template_path(path):
        return False
    return any(
        rule
        for rule, _severity in _match_path_rules(path)
        if rule
        in {
            "smartfuelpass_session_cookie_file",
            "smartfuelpass_auto_login_file",
            "environment_secret_file",
            "softlink_auth_file",
        }
    )


def _looks_placeholder(text: str) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _looks_dynamic_or_nonsecret_code(line: str) -> bool:
    stripped = line.strip()
    if any(marker in stripped for marker in ("{", "}", "$", "%", "config(", "os.environ")):
        return True
    lowered = stripped.casefold()
    return any(
        marker in lowered
        for marker in (
            "password_hash",
            "current_password",
            "new_password",
            "old_password",
            "verify_password",
            "password_status",
        )
    )


def _rule_applies_to_path(rule: str, path: str) -> bool:
    suffix = PurePosixPath(_normalize_path(path)).suffix.lower()
    if rule == "connection_string_password" and suffix in CODE_SUFFIXES:
        return False
    return True


def tracked_paths(project_root: Path) -> tuple[str, ...]:
    output = _run_git(project_root, "ls-files", "-z").stdout
    return tuple(sorted(_normalize_path(path) for path in _split_z(output)))


def untracked_paths(project_root: Path) -> tuple[str, ...]:
    output = _run_git(
        project_root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    ).stdout
    return tuple(sorted(_normalize_path(path) for path in _split_z(output)))


def scan_path_inventory(paths: Iterable[str], *, scope: str) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(set(paths)):
        for rule, severity in _match_path_rules(path):
            findings.append(Finding(scope=scope, rule=rule, severity=severity, path=path))
    return findings


def _read_text_if_small(path: Path) -> str | None:
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        return None
    data = path.read_bytes()
    if b"\0" in data:
        return None
    return data.decode("utf-8", errors="replace")


def _is_text_source_path(path: str) -> bool:
    normalized = PurePosixPath(_normalize_path(path))
    return normalized.name in TEXT_SOURCE_NAMES or normalized.suffix.lower() in TEXT_SOURCE_SUFFIXES


def _git_blob_text_if_small(project_root: Path, commit: str, path: str) -> str | None:
    if not _is_text_source_path(path):
        return None
    object_ref = f"{commit}:{path}"
    size = _run_git(project_root, "cat-file", "-s", object_ref, check=False)
    if size.returncode != 0:
        return None
    try:
        if int(size.stdout.strip()) > MAX_FILE_BYTES:
            return None
    except ValueError:
        return None
    completed = subprocess.run(
        ["git", "show", object_ref],
        cwd=project_root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0 or b"\0" in completed.stdout:
        return None
    return completed.stdout.decode("utf-8", errors="replace")


def _scan_text(
    text: str,
    *,
    scope: str,
    path: str,
    commit: str | None = None,
    per_text_limit: int | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if per_text_limit is not None and len(findings) >= per_text_limit:
            break
        if _looks_placeholder(line):
            continue
        for rule, pattern, severity in SECRET_PATTERNS:
            if not _rule_applies_to_path(rule, path):
                continue
            if rule in {"connection_string_password", "url_embedded_credentials"} and _looks_dynamic_or_nonsecret_code(line):
                continue
            if pattern.search(line):
                findings.append(
                    Finding(
                        scope=scope,
                        rule=rule,
                        severity=severity,
                        path=path,
                        line=line_number,
                        commit=commit[:12] if commit else None,
                    )
                )
    return findings


def scan_worktree_content(project_root: Path, paths: Iterable[str]) -> list[Finding]:
    findings: list[Finding] = []
    for relative_path in sorted(set(paths)):
        if _is_sensitive_path(relative_path) or _is_content_scan_excluded(relative_path):
            continue
        text = _read_text_if_small(project_root / PurePosixPath(relative_path))
        if text is None:
            continue
        findings.extend(_scan_text(text, scope="worktree_content", path=relative_path))
    return findings


def history_paths(project_root: Path) -> dict[str, set[str]]:
    completed = _run_git(
        project_root,
        "log",
        "--all",
        "--name-only",
        "--pretty=format:commit:%H",
    )
    current_commit: str | None = None
    paths_by_commit: dict[str, set[str]] = {}
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("commit:"):
            current_commit = line.removeprefix("commit:")
            paths_by_commit.setdefault(current_commit, set())
            continue
        if current_commit:
            paths_by_commit[current_commit].add(_normalize_path(line))
    return paths_by_commit


def scan_history_path_inventory(project_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, str, str]] = set()
    for commit, paths in history_paths(project_root).items():
        for path in paths:
            for rule, severity in _match_path_rules(path):
                key = (commit, path, rule)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    Finding(
                        scope="history_path",
                        rule=rule,
                        severity=severity,
                        path=path,
                        commit=commit[:12],
                    )
                )
    return findings


def scan_history_content(project_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, str, int, str]] = set()

    for commit, paths in history_paths(project_root).items():
        match_count = 0
        for path in sorted(paths):
            if match_count >= MAX_HISTORY_MATCHES_PER_COMMIT:
                break
            if _is_sensitive_path(path):
                continue
            if _is_content_scan_excluded(path):
                continue
            text = _git_blob_text_if_small(project_root, commit, path)
            if text is None:
                continue
            for finding in _scan_text(
                text,
                scope="history_content",
                path=path,
                commit=commit,
                per_text_limit=MAX_HISTORY_MATCHES_PER_COMMIT - match_count,
            ):
                key = (commit, path, finding.line or 0, finding.rule)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(finding)
                match_count += 1
    return findings


def summarize(findings: Iterable[Finding]) -> dict[str, int]:
    summary = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for finding in findings:
        summary[finding.severity] = summary.get(finding.severity, 0) + 1
    return summary


def build_report(project_root: Path, *, include_history: bool) -> dict[str, object]:
    tracked = tracked_paths(project_root)
    untracked = untracked_paths(project_root)
    findings: list[Finding] = []
    findings.extend(scan_path_inventory(tracked, scope="tracked_path"))
    findings.extend(scan_path_inventory(untracked, scope="untracked_path"))
    findings.extend(scan_worktree_content(project_root, (*tracked, *untracked)))
    if include_history:
        findings.extend(scan_history_path_inventory(project_root))
        findings.extend(scan_history_content(project_root))

    ordered = sorted(
        findings,
        key=lambda item: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(item.severity, 9),
            item.scope,
            item.path,
            item.line or 0,
            item.commit or "",
            item.rule,
        ),
    )
    summary = summarize(ordered)
    status = "ok" if not ordered else "findings"
    return {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "raw_values": "not_included",
        "history_scanned": include_history,
        "summary": summary,
        "finding_count": len(ordered),
        "findings": [finding.to_json() for finding in ordered],
    }


def write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan tracked files and Git history for sensitive artifacts without printing raw values."
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--history", action="store_true", help="Scan all reachable Git history.")
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    report = build_report(args.project_root.resolve(), include_history=args.history)
    if args.output:
        write_report(args.output, report)
    print(
        "Secret hygiene scan completed: "
        f"status={report['status']} findings={report['finding_count']} "
        f"raw_values={report['raw_values']}"
    )
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
