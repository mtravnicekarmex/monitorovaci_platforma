import datetime
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard.kalorimetry_shared import add_time_semantics_columns
from moduly.mereni.time_semantics import (
    SOURCE_TIMEZONE_EUROPE_PRAGUE,
    TIME_BASIS_EUROPE_PRAGUE_CIVIL,
    TIMESTAMP_POSITION_INSTANT,
    get_default_time_semantics,
)


def test_kalorimetry_default_time_semantics_is_prague_civil_instant():
    semantics = get_default_time_semantics("KALORIMETRY")

    assert semantics.time_basis == TIME_BASIS_EUROPE_PRAGUE_CIVIL
    assert semantics.source_timezone == SOURCE_TIMEZONE_EUROPE_PRAGUE
    assert semantics.timestamp_position == TIMESTAMP_POSITION_INSTANT


def test_add_time_semantics_columns_adds_canonical_utc_for_winter_and_summer_rows():
    result = add_time_semantics_columns(
        pd.DataFrame(
            [
                {"date": datetime.datetime(2026, 2, 11, 17, 17), "spotreba_energie": 10.0},
                {"date": datetime.datetime(2026, 5, 14, 11, 17), "spotreba_energie": 11.0},
            ]
        )
    )

    assert result["source_date"].tolist() == [
        datetime.datetime(2026, 2, 11, 17, 17),
        datetime.datetime(2026, 5, 14, 11, 17),
    ]
    assert result["time_utc"].dt.to_pydatetime().tolist() == [
        datetime.datetime(2026, 2, 11, 16, 17, tzinfo=datetime.timezone.utc),
        datetime.datetime(2026, 5, 14, 9, 17, tzinfo=datetime.timezone.utc),
    ]
    assert result["time_basis"].tolist() == [TIME_BASIS_EUROPE_PRAGUE_CIVIL] * 2
    assert result["source_timezone"].tolist() == [SOURCE_TIMEZONE_EUROPE_PRAGUE] * 2
    assert result["source_utc_offset_minutes"].tolist() == [60, 120]
    assert result["timestamp_position"].tolist() == [TIMESTAMP_POSITION_INSTANT] * 2
