from __future__ import annotations

import json

from moduly.mereni.kalorimetry.reconciliation import (
    run_historical_reconciliation_dry_run,
)


if __name__ == "__main__":
    summary = run_historical_reconciliation_dry_run()
    print(
        json.dumps(
            summary.to_dict(),
            default=str,
            sort_keys=True,
        )
    )
