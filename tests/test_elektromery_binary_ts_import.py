import math
import struct
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.elektromery.database.binary_ts_import import (
    BINARY_METER_CONFIGS,
    BinaryMeterFileConfig,
    binary_meter_config_from_mapping,
    binary_source_file_changed,
    build_sample_quality_runs,
    build_delta_source_rows,
    build_delta_source_rows_from_raw_rows,
    parse_binary_meter_file,
    sample_index_to_timestamp,
    summarize_parsed_file,
)


def _payload(values):
    return b"".join(struct.pack("<d", value) for value in values)


def test_parse_binary_meter_file_assigns_timestamps_and_skips_non_finite_values():
    config = BinaryMeterFileConfig(
        key="test",
        file_name="test.ts",
        identifikace="TS test",
        seriove_cislo=123,
        first_timestamp=datetime(2024, 7, 1, 0, 0, 0),
        timestamp_offset=timedelta(hours=1),
        interval_minutes=15,
        source_name="BINARY_TEST",
    )

    parsed = parse_binary_meter_file(config, _payload([0.0, 1.25, math.nan, 2.5]))

    assert parsed.sample_count == 4
    assert parsed.finite_count == 3
    assert parsed.skipped_non_finite_count == 1
    assert parsed.first_timestamp == datetime(2024, 7, 1, 1, 0, 0)
    assert parsed.last_timestamp == datetime(2024, 7, 1, 1, 45, 0)
    assert [(row.sample_index, row.date, row.delta) for row in parsed.measurements] == [
        (0, datetime(2024, 7, 1, 1, 0, 0), 0.0),
        (1, datetime(2024, 7, 1, 1, 15, 0), 1.25),
        (3, datetime(2024, 7, 1, 1, 45, 0), 2.5),
    ]


def test_parse_binary_meter_file_can_start_after_previous_checkpoint():
    config = BinaryMeterFileConfig(
        key="test",
        file_name="test.ts",
        identifikace="TS test",
        seriove_cislo=123,
        first_timestamp=datetime(2024, 7, 1, 0, 0, 0),
        timestamp_offset=timedelta(hours=1),
        interval_minutes=15,
        source_name="BINARY_TEST",
    )

    parsed = parse_binary_meter_file(config, _payload([1.0, 2.0, math.nan, 4.0]), start_sample_index=2)

    assert parsed.sample_count == 4
    assert parsed.finite_count == 1
    assert parsed.skipped_non_finite_count == 1
    assert parsed.measurements[0].sample_index == 3
    assert parsed.measurements[0].date == datetime(2024, 7, 1, 1, 45, 0)
    assert parsed.measurements[0].delta == 4.0


def test_build_delta_source_rows_prepares_rows_for_existing_elektromery_import():
    config = BinaryMeterFileConfig(
        key="test",
        file_name="test.ts",
        identifikace="TS test",
        seriove_cislo=123,
        first_timestamp=datetime(2024, 7, 1, 0, 0, 0),
        timestamp_offset=timedelta(hours=1),
        interval_minutes=15,
        source_name="BINARY_TEST",
    )
    parsed = parse_binary_meter_file(config, _payload([0.5]))

    rows = build_delta_source_rows(parsed)

    assert rows == [
        {
            "recid": 1,
            "identifikace": "TS test",
            "seriove_cislo": 123,
            "date": datetime(2024, 7, 1, 1, 0, 0),
            "objem": None,
            "delta": 0.5,
            "interval_minutes": 15,
            "platne": True,
            "delta_source": True,
        }
    ]


def test_build_delta_source_rows_from_raw_rows_uses_stable_sample_source_recid():
    config = BinaryMeterFileConfig(
        key="test",
        file_name="test.ts",
        identifikace="TS test",
        seriove_cislo=123,
        first_timestamp=datetime(2024, 7, 1, 0, 0, 0),
        timestamp_offset=timedelta(hours=1),
        interval_minutes=15,
        source_name="BINARY_TEST",
    )

    rows = build_delta_source_rows_from_raw_rows(
        config,
        [
            {
                "sample_index": 8,
                "identifikace": "TS test",
                "seriove_cislo": 123,
                "date": datetime(2024, 7, 1, 3, 0, 0),
                "delta": 1.5,
            }
        ],
    )

    assert rows == [
        {
            "recid": 9,
            "identifikace": "TS test",
            "seriove_cislo": 123,
            "date": datetime(2024, 7, 1, 3, 0, 0),
            "objem": None,
            "delta": 1.5,
            "interval_minutes": 15,
            "platne": True,
            "delta_source": True,
        }
    ]


def test_19891_config_uses_requested_metadata():
    config = BINARY_METER_CONFIGS["19891"]

    assert config.file_name == "19891.ts"
    assert config.identifikace == "TS1 - přetoky"
    assert config.seriove_cislo == 859182400407782429
    assert config.first_timestamp == datetime(2024, 7, 1, 0, 0, 0)
    assert config.timestamp_offset == timedelta(hours=1)
    assert config.interval_minutes == 15
    assert config.source_name == "BINARY_19891"
    assert sample_index_to_timestamp(config, 104) == datetime(2024, 7, 2, 3, 0, 0)


def test_binary_meter_config_from_mapping_reads_db_config_values():
    config = binary_meter_config_from_mapping(
        {
            "source_key": "19891",
            "file_name": "19891.ts",
            "identifikace": "TS1 - přetoky",
            "seriove_cislo": 859182400407782429,
            "first_timestamp": datetime(2024, 7, 1, 0, 0, 0),
            "timestamp_offset_minutes": 60,
            "interval_minutes": 15,
            "source_name": "BINARY_19891",
            "double_format": "<d",
        }
    )

    assert config == BINARY_METER_CONFIGS["19891"]


def test_binary_source_file_changed_detects_new_or_updated_source_state():
    current_mtime = datetime(2026, 5, 13, 8, 0, 0)

    assert binary_source_file_changed(
        current_byte_size=100,
        current_mtime=current_mtime,
        previous_byte_size=None,
        previous_mtime=current_mtime,
    )
    assert binary_source_file_changed(
        current_byte_size=100,
        current_mtime=current_mtime,
        previous_byte_size=99,
        previous_mtime=current_mtime,
    )
    assert binary_source_file_changed(
        current_byte_size=100,
        current_mtime=current_mtime,
        previous_byte_size=100,
        previous_mtime=datetime(2026, 5, 13, 7, 59, 59),
    )
    assert not binary_source_file_changed(
        current_byte_size=100,
        current_mtime=current_mtime,
        previous_byte_size=100,
        previous_mtime=current_mtime,
    )


def test_summarize_parsed_file_reports_basic_quality_metrics():
    config = BinaryMeterFileConfig(
        key="test",
        file_name="test.ts",
        identifikace="TS test",
        seriove_cislo=123,
        first_timestamp=datetime(2024, 7, 1, 0, 0, 0),
        timestamp_offset=timedelta(hours=1),
        interval_minutes=15,
        source_name="BINARY_TEST",
    )
    parsed = parse_binary_meter_file(config, _payload([0.0, 1.0, math.inf, 2.0]))

    summary = summarize_parsed_file(parsed)

    assert summary["sample_count"] == 4
    assert summary["finite_count"] == 3
    assert summary["skipped_non_finite_count"] == 1
    assert summary["positive_count"] == 2
    assert summary["zero_count"] == 1
    assert summary["total_delta"] == 3.0


def test_build_sample_quality_runs_groups_finite_and_missing_segments():
    config = BinaryMeterFileConfig(
        key="test",
        file_name="test.ts",
        identifikace="TS test",
        seriove_cislo=123,
        first_timestamp=datetime(2024, 7, 1, 0, 0, 0),
        timestamp_offset=timedelta(hours=1),
        interval_minutes=15,
        source_name="BINARY_TEST",
    )

    runs = build_sample_quality_runs(config, _payload([0.0, 1.0, math.nan, math.inf, 2.0]))

    assert [(run.status, run.start_sample_index, run.end_sample_index, run.sample_count) for run in runs] == [
        ("finite", 0, 1, 2),
        ("missing", 2, 3, 2),
        ("finite", 4, 4, 1),
    ]
    assert runs[1].start_timestamp == datetime(2024, 7, 1, 1, 30, 0)
    assert runs[1].end_timestamp == datetime(2024, 7, 1, 1, 45, 0)
