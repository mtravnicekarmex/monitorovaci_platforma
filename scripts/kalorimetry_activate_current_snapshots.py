from __future__ import annotations

import argparse
from datetime import datetime
import json

from moduly.mereni.kalorimetry.current_snapshot_activation import (
    activate_kalorimetry_current_snapshots,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Activate one approved kalorimetry current snapshot batch."
    )
    parser.add_argument("--confirm-current-snapshot-write", action="store_true")
    args = parser.parse_args()
    result = activate_kalorimetry_current_snapshots(
        reference_time=datetime(2026, 8, 3, 8, 0),
        expected_period_start=datetime(2026, 8, 3),
        expected_period_end=datetime(2026, 8, 10),
        expected_available_identifier_count=8,
        expected_unavailable_identifier_count=6,
        confirm_activation=args.confirm_current_snapshot_write,
    )
    print(
        json.dumps(
            result.to_aggregate_dict(),
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
