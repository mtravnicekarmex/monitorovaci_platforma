from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


REMOTE_AUDIT_WRAP_EVENT = "monitoring_orchestrator_remote_audit_wrapped"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "wrap-remote-audit":
            return _wrap_remote_audit(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"orchestrator export CLI error: {exc}") from exc
    raise SystemExit("orchestrator export CLI error: unsupported command")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare sanitized file-only inputs for the monitoring orchestrator."
        )
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    wrap = subcommands.add_parser(
        "wrap-remote-audit",
        help=(
            "Read a sanitized run_monitoring_agent.py --audit-state JSON object "
            "and add a timezone-aware captured_at timestamp."
        ),
    )
    wrap.add_argument(
        "--input",
        type=Path,
        help="Input JSON file. If omitted, JSON is read from stdin.",
    )
    wrap.add_argument(
        "--output",
        type=Path,
        help="Output JSON file. If omitted, wrapped JSON is written to stdout.",
    )
    wrap.add_argument(
        "--captured-at",
        help=(
            "Timezone-aware ISO-8601 capture timestamp. Defaults to current UTC "
            "time at wrapper execution."
        ),
    )
    return parser


def _wrap_remote_audit(args: argparse.Namespace) -> int:
    captured_at = _parse_captured_at(args.captured_at)
    payload = _read_json_payload(args.input)
    wrapped = wrap_remote_audit_payload(payload, captured_at=captured_at)
    _emit_wrapped_payload(wrapped, output_path=args.output)
    return 0


def wrap_remote_audit_payload(
    payload: object,
    *,
    captured_at: datetime,
) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise ValueError("remote audit payload must be a JSON object")
    if payload.get("event") != "agent_state_audit":
        raise ValueError("remote audit event must be agent_state_audit")
    audit_contract_version = payload.get("audit_contract_version")
    if (
        isinstance(audit_contract_version, bool)
        or not isinstance(audit_contract_version, int)
        or audit_contract_version < 1
    ):
        raise ValueError("audit_contract_version must be a positive integer")
    _require_aware_datetime(captured_at, context="captured_at")

    wrapped = dict(payload)
    wrapped["captured_at"] = _format_datetime(captured_at)
    return wrapped


def _read_json_payload(path: Path | None) -> object:
    if path is None:
        content = sys.stdin.read()
    else:
        resolved = path.resolve()
        _reject_env_path(resolved)
        content = resolved.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError("remote audit input is empty")
    return json.loads(content)


def _emit_wrapped_payload(
    payload: Mapping[str, object],
    *,
    output_path: Path | None,
) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output_path is None:
        sys.stdout.write(content)
        return

    resolved = output_path.resolve()
    _reject_env_path(resolved)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    sys.stdout.write(
        json.dumps(
            {
                "captured_at": payload["captured_at"],
                "event": REMOTE_AUDIT_WRAP_EVENT,
                "output_path": str(resolved),
                "status": "wrapped",
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    sys.stdout.write("\n")


def _parse_captured_at(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("captured_at must be an ISO-8601 datetime") from exc
    _require_aware_datetime(parsed, context="captured_at")
    return parsed


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_aware_datetime(value: datetime, *, context: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{context} must be timezone-aware")


def _reject_env_path(path: Path) -> None:
    if any(part.lower() == ".env" for part in path.parts):
        raise ValueError("env_source_forbidden")
    if path.name.lower().startswith(".env"):
        raise ValueError("env_source_forbidden")


if __name__ == "__main__":
    raise SystemExit(main())
