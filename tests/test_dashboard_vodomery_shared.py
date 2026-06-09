import datetime
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard.vodomery_shared import align_latest_hour_timestamp


def test_align_latest_hour_timestamp_moves_only_current_hour_rows():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2026-06-09 05:00:00",
                    "2026-06-09 06:00:00",
                    "2026-06-09 07:00:00",
                ]
            ),
            "value": [1.0, 2.0, 3.0],
        }
    )

    aligned = align_latest_hour_timestamp(
        frame,
        datetime.datetime(2026, 6, 9, 6, 45, 49),
    )

    assert aligned["date"].tolist() == [
        pd.Timestamp("2026-06-09 05:00:00"),
        pd.Timestamp("2026-06-09 06:45:49"),
        pd.Timestamp("2026-06-09 07:00:00"),
    ]
    assert frame["date"].iloc[1] == pd.Timestamp("2026-06-09 06:00:00")
