from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .orchestrator import (
    OrchestratorError,
    build_orchestrator_snapshot,
    load_registry_file,
    render_orchestrator_snapshot,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a file-only/shadow-only monitoring orchestrator snapshot "
            "from supplied sanitized agent snapshots."
        )
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    run = subcommands.add_parser(
        "run",
        help="Correlate sanitized file-only source snapshots from a registry.",
    )
    run.add_argument("--registry-file", type=Path, required=True)
    run.add_argument("--json-output", type=Path)
    run.add_argument("--markdown-output", type=Path)
    run.add_argument(
        "--print-markdown",
        action="store_true",
        help=(
            "Print the bounded Markdown summary instead of compact JSON when "
            "no output file is requested."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return _run(args)
    except (OSError, OrchestratorError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"orchestrator CLI error: {exc}") from exc
    raise SystemExit("orchestrator CLI error: unsupported command")


def _run(args: argparse.Namespace) -> int:
    registry_entries = load_registry_file(args.registry_file)
    snapshot = build_orchestrator_snapshot(registry_entries)
    payload = snapshot.to_dict()
    markdown = render_orchestrator_snapshot(snapshot)

    if args.json_output is not None:
        _write_text(
            args.json_output,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    if args.markdown_output is not None:
        _write_text(args.markdown_output, markdown)

    if args.json_output is None and args.markdown_output is None:
        if args.print_markdown:
            sys.stdout.write(markdown)
        else:
            sys.stdout.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            sys.stdout.write("\n")
    return 0


def _write_text(path: Path, content: str) -> None:
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
