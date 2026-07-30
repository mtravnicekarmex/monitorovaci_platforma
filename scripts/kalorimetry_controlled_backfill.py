from __future__ import annotations

import argparse
import json

from moduly.mereni.kalorimetry.production_backfill import (
    run_controlled_kalorimetry_backfill,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Controlled kalorimetry historical prediction backfill."
    )
    parser.add_argument("mode", choices=("apply",))
    parser.add_argument(
        "--confirm-controlled-write",
        action="store_true",
        help="Required explicit confirmation for production writes.",
    )
    parser.add_argument("--max-weeks", type=int, default=None)
    args = parser.parse_args()
    result = run_controlled_kalorimetry_backfill(
        confirm_apply=args.confirm_controlled_write,
        max_weeks=args.max_weeks,
    )
    print(
        json.dumps(
            result.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
