import datetime
import warnings

import pandas as pd

from services.api.services.vodomery import _prepare_branch_measurements, _serialize_dataframe_rows


def test_serialize_dataframe_rows_converts_datetime_columns_without_future_warning():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-04-09 10:15:00", None]),
            "value": [1, 2],
        }
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        rows = _serialize_dataframe_rows(frame)

    assert rows[0]["date"] == datetime.datetime(2026, 4, 9, 10, 15)
    assert isinstance(rows[0]["date"], datetime.datetime)
    assert rows[1]["date"] is None
    assert rows[0]["value"] == 1
    assert rows[1]["value"] == 2


def test_prepare_branch_measurements_zeroes_invalid_rows():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2026-04-10 10:00:00",
                    "2026-04-10 10:15:00",
                    "2026-04-10 10:30:00",
                ]
            ),
            "identifikace": ["A", "A", "A"],
            "objem": [100.0, 120.0, 100.6],
            "delta": [None, None, 0.6],
            "platne": [True, False, True],
            "reset_detected": [False, False, False],
        }
    )

    prepared = _prepare_branch_measurements(frame)

    assert prepared["spotreba"].tolist() == [0.0, 0.0, 0.6]
