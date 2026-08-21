from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from .incident_store import IncidentStateStore, IncidentStoreError
from .shadow_pilot import (
    SOURCE_LEGACY_ALERT,
    SOURCE_MONITORING_AGENT,
    ShadowPilotEvent,
    blind_spots_from_shadow_pilot_payload,
    build_shadow_pilot_comparison,
    events_from_incident_transition_records,
    events_from_shadow_pilot_payload,
    render_shadow_pilot_comparison,
    shadow_pilot_events_payload,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build read-only shadow-pilot comparison outputs from supplied "
            "sanitized monitoring-agent and legacy-alert events."
        )
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    export_agent = subcommands.add_parser(
        "export-agent-events",
        help="Export comparable monitoring-agent events from incident_state.json.",
    )
    export_agent.add_argument("--agent-state-file", type=Path, required=True)
    export_agent.add_argument("--period-start", required=True)
    export_agent.add_argument("--period-end", required=True)
    export_agent.add_argument("--json-output", type=Path)

    compare = subcommands.add_parser(
        "compare",
        help="Compare monitoring-agent events against supplied legacy-alert events.",
    )
    agent_input = compare.add_mutually_exclusive_group(required=True)
    agent_input.add_argument("--agent-state-file", type=Path)
    agent_input.add_argument("--agent-events-file", type=Path)
    compare.add_argument("--legacy-events-file", type=Path, required=True)
    compare.add_argument("--blind-spots-file", type=Path)
    compare.add_argument("--period-start", required=True)
    compare.add_argument("--period-end", required=True)
    compare.add_argument("--match-window-seconds", type=float, default=300.0)
    compare.add_argument("--duplicate-window-seconds", type=float, default=300.0)
    compare.add_argument("--json-output", type=Path)
    compare.add_argument("--markdown-output", type=Path)
    compare.add_argument(
        "--print-markdown",
        action="store_true",
        help="Print the bounded Markdown summary instead of JSON when no output file is requested.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "export-agent-events":
            return _export_agent_events(args)
        if args.command == "compare":
            return _compare(args)
    except (OSError, ValueError, IncidentStoreError, json.JSONDecodeError) as exc:
        raise SystemExit(f"shadow pilot CLI error: {exc}") from exc
    raise SystemExit("shadow pilot CLI error: unsupported command")


def _export_agent_events(args: argparse.Namespace) -> int:
    period_start = _parse_datetime_argument(args.period_start, context="period_start")
    period_end = _parse_datetime_argument(args.period_end, context="period_end")
    events = _filter_events_for_period(
        _load_agent_events_from_state_file(args.agent_state_file),
        period_start=period_start,
        period_end=period_end,
    )
    payload = shadow_pilot_events_payload(
        events,
        source=SOURCE_MONITORING_AGENT,
    )
    _emit_json(payload, output_path=args.json_output)
    return 0


def _compare(args: argparse.Namespace) -> int:
    period_start = _parse_datetime_argument(args.period_start, context="period_start")
    period_end = _parse_datetime_argument(args.period_end, context="period_end")
    if args.agent_state_file is not None:
        agent_events = _load_agent_events_from_state_file(args.agent_state_file)
    else:
        agent_events = _load_event_payload(
            args.agent_events_file,
            default_source=SOURCE_MONITORING_AGENT,
        )
    legacy_events = _load_event_payload(
        args.legacy_events_file,
        default_source=SOURCE_LEGACY_ALERT,
    )
    blind_spots = (
        blind_spots_from_shadow_pilot_payload(_read_json(args.blind_spots_file))
        if args.blind_spots_file is not None
        else ()
    )
    comparison = build_shadow_pilot_comparison(
        period_start=period_start,
        period_end=period_end,
        agent_events=agent_events,
        legacy_events=legacy_events,
        blind_spots=blind_spots,
        match_window_seconds=args.match_window_seconds,
        duplicate_window_seconds=args.duplicate_window_seconds,
    )
    payload = comparison.to_dict()
    markdown = render_shadow_pilot_comparison(comparison)

    if args.json_output is not None:
        _write_text(
            args.json_output,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    if args.markdown_output is not None:
        _write_text(args.markdown_output, markdown)

    if args.json_output is None and args.markdown_output is None:
        if args.print_markdown:
            print(markdown)
        else:
            print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


def _load_agent_events_from_state_file(path: Path) -> tuple[ShadowPilotEvent, ...]:
    resolved = path.resolve()
    if resolved.name != "incident_state.json":
        raise ValueError("agent state file must be named incident_state.json")
    snapshot = IncidentStateStore(resolved.parent).load()
    return events_from_incident_transition_records(snapshot.transition_records)


def _load_event_payload(
    path: Path,
    *,
    default_source: str,
) -> tuple[ShadowPilotEvent, ...]:
    return events_from_shadow_pilot_payload(
        _read_json(path),
        default_source=default_source,
    )


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _emit_json(payload: dict[str, object], *, output_path: Path | None) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output_path is None:
        sys.stdout.write(content)
        return
    _write_text(output_path, content)


def _write_text(path: Path, content: str) -> None:
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")


def _filter_events_for_period(
    events: tuple[ShadowPilotEvent, ...],
    *,
    period_start: datetime,
    period_end: datetime,
) -> tuple[ShadowPilotEvent, ...]:
    if period_start >= period_end:
        raise ValueError("period_start must be before period_end")
    return tuple(
        event
        for event in events
        if period_start <= event.occurred_at < period_end
    )


def _parse_datetime_argument(value: str, *, context: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{context} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{context} must be timezone-aware")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
