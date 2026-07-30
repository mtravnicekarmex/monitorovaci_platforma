from __future__ import annotations

import argparse
import json

from moduly.mereni.plynomery.reconciliation import (
    reconciliation_approval_sha256,
    run_active_period_reconciliation_apply,
    run_active_period_reconciliation_dry_run,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate-only active-period plynomery reconciliation."
    )
    parser.add_argument(
        "command",
        choices=("dry-run", "apply"),
        help="Inspect the scope or apply one explicitly approved scope.",
    )
    parser.add_argument(
        "--approved-dry-run-sha256",
        help="Required for apply; binds the write to an exact dry-run summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "dry-run":
        summary = run_active_period_reconciliation_dry_run()
        result = summary.to_dict()
        result["approval_sha256"] = reconciliation_approval_sha256(summary)
    else:
        if not args.approved_dry_run_sha256:
            raise SystemExit(
                "apply requires --approved-dry-run-sha256 from an approved dry-run"
            )
        result = run_active_period_reconciliation_apply(
            approved_dry_run_sha256=args.approved_dry_run_sha256,
        ).to_dict()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
