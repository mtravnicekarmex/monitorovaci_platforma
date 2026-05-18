from __future__ import annotations

import logging
import math
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.db.connect import ENGINE_PG, SessionLocalPG
from moduly.mereni.elektromery.database.elektromery_db_vse import import_measurements
from moduly.mereni.elektromery.database.time_semantics import (
    BINARY_TIME_SEMANTICS,
    build_time_columns,
)


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DOUBLE_SIZE_BYTES = 8
BINARY_IMPORT_CHUNK_SIZE = 5000
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BinaryMeterFileConfig:
    key: str
    file_name: str
    identifikace: str
    seriove_cislo: int | None
    first_timestamp: datetime
    timestamp_offset: timedelta
    interval_minutes: int
    source_name: str
    double_format: str = "<d"
    time_basis: str = BINARY_TIME_SEMANTICS.time_basis
    source_timezone: str = BINARY_TIME_SEMANTICS.source_timezone
    source_utc_offset_minutes: int | None = BINARY_TIME_SEMANTICS.source_utc_offset_minutes
    timestamp_position: str = BINARY_TIME_SEMANTICS.timestamp_position
    time_fold: int | None = BINARY_TIME_SEMANTICS.time_fold

    @property
    def first_db_timestamp(self) -> datetime:
        return self.first_timestamp + self.timestamp_offset

    @property
    def file_path(self) -> Path:
        return DATA_DIR / self.file_name


@dataclass(frozen=True)
class BinaryMeterImportResult:
    config: BinaryMeterFileConfig
    byte_size: int
    previous_last_sample_index: int
    new_last_sample_index: int
    parsed_sample_count: int
    finite_measurements: int
    skipped_non_finite_count: int
    inserted_raw_measurements: int
    monitoring_rows: int


@dataclass(frozen=True)
class BinaryMeterMonitoringBackfillResult:
    config: BinaryMeterFileConfig
    raw_rows: int
    monitoring_rows_before: int
    monitoring_rows_after: int
    monitoring_rows_added: int
    prepared_monitoring_rows: int


@dataclass(frozen=True)
class BinaryMeterSourceSyncResult:
    config: BinaryMeterFileConfig
    changed: bool
    reason: str
    byte_size: int
    previous_byte_size: int | None
    source_mtime: datetime
    previous_mtime: datetime | None
    import_result: BinaryMeterImportResult | None
    backfill_result: BinaryMeterMonitoringBackfillResult | None


@dataclass(frozen=True)
class BinaryMeterMeasurement:
    sample_index: int
    date: datetime
    delta: float


@dataclass(frozen=True)
class BinaryMeterSampleRun:
    status: str
    start_sample_index: int
    end_sample_index: int
    start_timestamp: datetime
    end_timestamp: datetime
    sample_count: int


@dataclass(frozen=True)
class ParsedBinaryMeterFile:
    config: BinaryMeterFileConfig
    byte_size: int
    sample_count: int
    measurements: tuple[BinaryMeterMeasurement, ...]
    skipped_non_finite_count: int
    negative_count: int

    @property
    def finite_count(self) -> int:
        return len(self.measurements)

    @property
    def first_timestamp(self) -> datetime | None:
        if self.sample_count <= 0:
            return None
        return self.config.first_db_timestamp

    @property
    def last_timestamp(self) -> datetime | None:
        if self.sample_count <= 0:
            return None
        return sample_index_to_timestamp(self.config, self.sample_count - 1)

    @property
    def first_measurement_timestamp(self) -> datetime | None:
        if not self.measurements:
            return None
        return self.measurements[0].date

    @property
    def last_measurement_timestamp(self) -> datetime | None:
        if not self.measurements:
            return None
        return self.measurements[-1].date

    @property
    def positive_count(self) -> int:
        return sum(1 for measurement in self.measurements if measurement.delta > 0)

    @property
    def zero_count(self) -> int:
        return sum(1 for measurement in self.measurements if measurement.delta == 0)

    @property
    def min_delta(self) -> float | None:
        if not self.measurements:
            return None
        return min(measurement.delta for measurement in self.measurements)

    @property
    def max_delta(self) -> float | None:
        if not self.measurements:
            return None
        return max(measurement.delta for measurement in self.measurements)

    @property
    def total_delta(self) -> float:
        return round(sum(measurement.delta for measurement in self.measurements), 6)


BINARY_METER_CONFIGS: dict[str, BinaryMeterFileConfig] = {
    "19891": BinaryMeterFileConfig(
        key="19891",
        file_name="19891.ts",
        identifikace="TS1 - přetoky",
        seriove_cislo=859182400407782429,
        first_timestamp=datetime(2024, 7, 1, 0, 0, 0),
        timestamp_offset=timedelta(0),
        interval_minutes=15,
        source_name="BINARY_19891",
    )
}


def read_binary_source(source: bytes | bytearray | BinaryIO | Path | str) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, bytearray):
        return bytes(source)
    if isinstance(source, (Path, str)):
        return Path(source).read_bytes()

    position = None
    if hasattr(source, "tell") and hasattr(source, "seek"):
        position = source.tell()
        source.seek(0)
    data = source.read()
    if position is not None:
        source.seek(position)
    return bytes(data)


def chunked(items, size: int = BINARY_IMPORT_CHUNK_SIZE):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def sample_index_to_timestamp(config: BinaryMeterFileConfig, sample_index: int) -> datetime:
    return config.first_db_timestamp + timedelta(minutes=config.interval_minutes * sample_index)


def _config_time_semantics_row(config: BinaryMeterFileConfig) -> dict[str, object]:
    return {
        "time_basis": config.time_basis,
        "source_timezone": config.source_timezone,
        "source_utc_offset_minutes": config.source_utc_offset_minutes,
        "timestamp_position": config.timestamp_position,
        "time_fold": config.time_fold,
    }


def binary_source_file_changed(
    *,
    current_byte_size: int,
    current_mtime: datetime,
    previous_byte_size: int | None,
    previous_mtime: datetime | None,
) -> bool:
    if previous_byte_size is None or previous_mtime is None:
        return True
    return int(previous_byte_size) != int(current_byte_size) or previous_mtime != current_mtime


def parse_binary_meter_file(
    config: BinaryMeterFileConfig,
    source: bytes | bytearray | BinaryIO | Path | str | None = None,
    *,
    start_sample_index: int = 0,
) -> ParsedBinaryMeterFile:
    payload = read_binary_source(config.file_path if source is None else source)
    if len(payload) % DOUBLE_SIZE_BYTES != 0:
        raise ValueError(
            f"Binary file size must be divisible by {DOUBLE_SIZE_BYTES} bytes, got {len(payload)}."
        )
    if start_sample_index < 0:
        raise ValueError("start_sample_index must be greater than or equal to 0.")

    measurements: list[BinaryMeterMeasurement] = []
    skipped_non_finite_count = 0
    negative_count = 0
    sample_count = len(payload) // DOUBLE_SIZE_BYTES

    if start_sample_index > sample_count:
        start_sample_index = sample_count

    offset = start_sample_index * DOUBLE_SIZE_BYTES
    for relative_index, (raw_value,) in enumerate(struct.iter_unpack(config.double_format, payload[offset:])):
        sample_index = start_sample_index + relative_index
        if not math.isfinite(raw_value):
            skipped_non_finite_count += 1
            continue

        value = round(float(raw_value), 6)
        if value < 0:
            negative_count += 1

        measurements.append(
            BinaryMeterMeasurement(
                sample_index=sample_index,
                date=sample_index_to_timestamp(config, sample_index),
                delta=value,
            )
        )

    return ParsedBinaryMeterFile(
        config=config,
        byte_size=len(payload),
        sample_count=sample_count,
        measurements=tuple(measurements),
        skipped_non_finite_count=skipped_non_finite_count,
        negative_count=negative_count,
    )


def build_sample_quality_runs(
    config: BinaryMeterFileConfig,
    source: bytes | bytearray | BinaryIO | Path | str | None = None,
) -> tuple[BinaryMeterSampleRun, ...]:
    payload = read_binary_source(config.file_path if source is None else source)
    if len(payload) % DOUBLE_SIZE_BYTES != 0:
        raise ValueError(
            f"Binary file size must be divisible by {DOUBLE_SIZE_BYTES} bytes, got {len(payload)}."
        )

    sample_count = len(payload) // DOUBLE_SIZE_BYTES
    if sample_count == 0:
        return ()

    runs: list[BinaryMeterSampleRun] = []
    current_status: str | None = None
    current_start = 0

    for sample_index, (raw_value,) in enumerate(struct.iter_unpack(config.double_format, payload)):
        status = "finite" if math.isfinite(raw_value) else "missing"
        if current_status is None:
            current_status = status
            current_start = sample_index
            continue
        if status != current_status:
            runs.append(
                _build_sample_run(config, current_status, current_start, sample_index - 1)
            )
            current_status = status
            current_start = sample_index

    runs.append(_build_sample_run(config, current_status or "missing", current_start, sample_count - 1))
    return tuple(runs)


def _build_sample_run(
    config: BinaryMeterFileConfig,
    status: str,
    start_sample_index: int,
    end_sample_index: int,
) -> BinaryMeterSampleRun:
    return BinaryMeterSampleRun(
        status=status,
        start_sample_index=start_sample_index,
        end_sample_index=end_sample_index,
        start_timestamp=sample_index_to_timestamp(config, start_sample_index),
        end_timestamp=sample_index_to_timestamp(config, end_sample_index),
        sample_count=end_sample_index - start_sample_index + 1,
    )


def build_delta_source_rows(parsed: ParsedBinaryMeterFile) -> list[dict[str, object]]:
    return [
        {
            "recid": measurement.sample_index + 1,
            "identifikace": parsed.config.identifikace,
            "seriove_cislo": parsed.config.seriove_cislo,
            "date": measurement.date,
            **_config_time_semantics_row(parsed.config),
            "objem": None,
            "delta": measurement.delta,
            "interval_minutes": parsed.config.interval_minutes,
            "platne": measurement.delta >= 0,
            "delta_source": True,
        }
        for measurement in parsed.measurements
    ]


def build_delta_source_rows_from_raw_rows(
    config: BinaryMeterFileConfig,
    raw_rows,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in raw_rows:
        sample_index = int(row["sample_index"])
        rows.append(
            {
                "recid": sample_index + 1,
                "identifikace": str(row["identifikace"]),
                "seriove_cislo": None if row["seriove_cislo"] is None else int(row["seriove_cislo"]),
                "date": row["date"],
                **_config_time_semantics_row(config),
                "objem": None,
                "delta": float(row["delta"]),
                "interval_minutes": config.interval_minutes,
                "platne": float(row["delta"]) >= 0,
                "delta_source": True,
            }
        )
    return rows


def ensure_binary_import_tables() -> None:
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS dbo"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dbo.elektromery_binary_source_configs (
                    source_key VARCHAR(100) PRIMARY KEY,
                    file_name VARCHAR(255) NOT NULL,
                    identifikace VARCHAR(250) NOT NULL,
                    seriove_cislo BIGINT,
                    first_timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                    timestamp_offset_minutes INTEGER NOT NULL DEFAULT 0,
                    interval_minutes INTEGER NOT NULL,
                    source_name VARCHAR(20) NOT NULL UNIQUE,
                    double_format VARCHAR(10) NOT NULL DEFAULT '<d',
                    time_basis VARCHAR(40) NOT NULL DEFAULT 'FIXED_OFFSET',
                    source_timezone VARCHAR(64) NOT NULL DEFAULT '+01:00',
                    source_utc_offset_minutes INTEGER,
                    timestamp_position VARCHAR(20) NOT NULL DEFAULT 'start',
                    time_fold INTEGER,
                    enabled BOOLEAN NOT NULL DEFAULT true,
                    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
                    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dbo."Mereni_elektromery_BINARY" (
                    recid BIGSERIAL PRIMARY KEY,
                    source_key VARCHAR(100) NOT NULL,
                    sample_index BIGINT NOT NULL,
                    identifikace VARCHAR(250) NOT NULL,
                    seriove_cislo BIGINT,
                    date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                    source_date TIMESTAMP WITHOUT TIME ZONE,
                    time_utc TIMESTAMP WITH TIME ZONE,
                    time_basis VARCHAR(40),
                    source_timezone VARCHAR(64),
                    source_utc_offset_minutes INTEGER,
                    time_fold INTEGER,
                    timestamp_position VARCHAR(20),
                    delta DOUBLE PRECISION NOT NULL,
                    source_file VARCHAR(255) NOT NULL,
                    source_byte_size BIGINT NOT NULL,
                    source_mtime TIMESTAMP WITHOUT TIME ZONE,
                    imported_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE dbo.elektromery_binary_source_configs
                    ADD COLUMN IF NOT EXISTS time_basis VARCHAR(40) NOT NULL DEFAULT 'FIXED_OFFSET',
                    ADD COLUMN IF NOT EXISTS source_timezone VARCHAR(64) NOT NULL DEFAULT '+01:00',
                    ADD COLUMN IF NOT EXISTS source_utc_offset_minutes INTEGER,
                    ADD COLUMN IF NOT EXISTS timestamp_position VARCHAR(20) NOT NULL DEFAULT 'start',
                    ADD COLUMN IF NOT EXISTS time_fold INTEGER
                """
            )
        )
        conn.execute(
            text(
                """
                ALTER TABLE dbo."Mereni_elektromery_BINARY"
                    ADD COLUMN IF NOT EXISTS source_date TIMESTAMP WITHOUT TIME ZONE,
                    ADD COLUMN IF NOT EXISTS time_utc TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN IF NOT EXISTS time_basis VARCHAR(40),
                    ADD COLUMN IF NOT EXISTS source_timezone VARCHAR(64),
                    ADD COLUMN IF NOT EXISTS source_utc_offset_minutes INTEGER,
                    ADD COLUMN IF NOT EXISTS time_fold INTEGER,
                    ADD COLUMN IF NOT EXISTS timestamp_position VARCHAR(20)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_ele_binary_source_sample
                ON dbo."Mereni_elektromery_BINARY" (source_key, sample_index)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_ele_binary_time_utc
                ON dbo."Mereni_elektromery_BINARY" (time_utc)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_ele_binary_source_date
                ON dbo."Mereni_elektromery_BINARY" (source_key, date)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_ele_binary_ident_date
                ON dbo."Mereni_elektromery_BINARY" (identifikace, date)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dbo.elektromery_binary_import_state (
                    source_key VARCHAR(100) PRIMARY KEY,
                    last_sample_index BIGINT NOT NULL DEFAULT -1,
                    last_byte_size BIGINT,
                    last_mtime TIMESTAMP WITHOUT TIME ZONE,
                    last_imported_at TIMESTAMP WITHOUT TIME ZONE,
                    last_status VARCHAR(20),
                    last_error TEXT,
                    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
                )
                """
            )
        )


def seed_default_binary_meter_configs() -> None:
    ensure_binary_import_tables()
    with ENGINE_PG.begin() as conn:
        for config in BINARY_METER_CONFIGS.values():
            conn.execute(
                text(
                    """
                    INSERT INTO dbo.elektromery_binary_source_configs (
                        source_key,
                        file_name,
                        identifikace,
                        seriove_cislo,
                        first_timestamp,
                        timestamp_offset_minutes,
                        interval_minutes,
                        source_name,
                        double_format,
                        time_basis,
                        source_timezone,
                        source_utc_offset_minutes,
                        timestamp_position,
                        time_fold,
                        enabled
                    )
                    VALUES (
                        :source_key,
                        :file_name,
                        :identifikace,
                        :seriove_cislo,
                        :first_timestamp,
                        :timestamp_offset_minutes,
                        :interval_minutes,
                        :source_name,
                        :double_format,
                        :time_basis,
                        :source_timezone,
                        :source_utc_offset_minutes,
                        :timestamp_position,
                        :time_fold,
                        true
                    )
                    ON CONFLICT (source_key) DO NOTHING
                    """
                ),
                _config_to_db_params(config),
            )


def load_binary_meter_configs(*, enabled_only: bool = True) -> dict[str, BinaryMeterFileConfig]:
    ensure_binary_import_tables()
    seed_default_binary_meter_configs()
    query = """
        SELECT
            source_key,
            file_name,
            identifikace,
            seriove_cislo,
            first_timestamp,
            timestamp_offset_minutes,
            interval_minutes,
            source_name,
            double_format,
            time_basis,
            source_timezone,
            source_utc_offset_minutes,
            timestamp_position,
            time_fold
        FROM dbo.elektromery_binary_source_configs
    """
    if enabled_only:
        query += " WHERE enabled = true"
    query += " ORDER BY source_key"

    with ENGINE_PG.connect() as conn:
        rows = conn.execute(text(query)).mappings().all()
    return {
        config.key: config
        for config in (binary_meter_config_from_mapping(row) for row in rows)
    }


def binary_meter_config_from_mapping(row) -> BinaryMeterFileConfig:
    return BinaryMeterFileConfig(
        key=str(row["source_key"]),
        file_name=str(row["file_name"]),
        identifikace=str(row["identifikace"]),
        seriove_cislo=None if row["seriove_cislo"] is None else int(row["seriove_cislo"]),
        first_timestamp=row["first_timestamp"],
        timestamp_offset=timedelta(minutes=int(row["timestamp_offset_minutes"] or 0)),
        interval_minutes=int(row["interval_minutes"]),
        source_name=str(row["source_name"]),
        double_format=str(row["double_format"] or "<d"),
        time_basis=str(row.get("time_basis") or BINARY_TIME_SEMANTICS.time_basis),
        source_timezone=str(row.get("source_timezone") or BINARY_TIME_SEMANTICS.source_timezone),
        source_utc_offset_minutes=(
            BINARY_TIME_SEMANTICS.source_utc_offset_minutes
            if row.get("source_utc_offset_minutes") is None
            else int(row["source_utc_offset_minutes"])
        ),
        timestamp_position=str(row.get("timestamp_position") or BINARY_TIME_SEMANTICS.timestamp_position),
        time_fold=None if row.get("time_fold") is None else int(row["time_fold"]),
    )


def import_binary_meter_source(
    config: BinaryMeterFileConfig,
    *,
    session: Session | None = None,
    write_to_monitoring: bool = True,
) -> BinaryMeterImportResult:
    ensure_binary_import_tables()
    owns_session = session is None
    db_session = session or SessionLocalPG()
    try:
        if owns_session:
            with db_session.begin():
                return _import_binary_meter_source_in_transaction(
                    db_session,
                    config,
                    write_to_monitoring=write_to_monitoring,
                )
        return _import_binary_meter_source_in_transaction(
            db_session,
            config,
            write_to_monitoring=write_to_monitoring,
        )
    finally:
        if owns_session:
            db_session.close()


def import_enabled_binary_meter_sources(*, write_to_monitoring: bool = True) -> dict[str, BinaryMeterImportResult]:
    configs = load_binary_meter_configs(enabled_only=True)
    results: dict[str, BinaryMeterImportResult] = {}
    with SessionLocalPG() as session:
        with session.begin():
            for config in configs.values():
                results[config.key] = _import_binary_meter_source_in_transaction(
                    session,
                    config,
                    write_to_monitoring=write_to_monitoring,
                )
    return results


def sync_changed_binary_meter_sources() -> dict[str, BinaryMeterSourceSyncResult]:
    configs = load_binary_meter_configs(enabled_only=True)
    results: dict[str, BinaryMeterSourceSyncResult] = {}
    with SessionLocalPG() as session:
        with session.begin():
            for config in configs.values():
                results[config.key] = _sync_changed_binary_meter_source_in_transaction(
                    session,
                    config,
                )
                _log_binary_meter_sync_result(results[config.key])
    return results


def backfill_binary_source_to_monitoring(
    config: BinaryMeterFileConfig,
    *,
    session: Session | None = None,
) -> BinaryMeterMonitoringBackfillResult:
    ensure_binary_import_tables()
    owns_session = session is None
    db_session = session or SessionLocalPG()
    try:
        if owns_session:
            with db_session.begin():
                return _backfill_binary_source_to_monitoring_in_transaction(db_session, config)
        return _backfill_binary_source_to_monitoring_in_transaction(db_session, config)
    finally:
        if owns_session:
            db_session.close()


def _sync_changed_binary_meter_source_in_transaction(
    session: Session,
    config: BinaryMeterFileConfig,
) -> BinaryMeterSourceSyncResult:
    source_stat = config.file_path.stat()
    source_mtime = datetime.fromtimestamp(source_stat.st_mtime)
    state = _load_import_state(session, config.key)
    previous_byte_size = None if state is None else state.get("last_byte_size")
    previous_mtime = None if state is None else state.get("last_mtime")
    changed = binary_source_file_changed(
        current_byte_size=source_stat.st_size,
        current_mtime=source_mtime,
        previous_byte_size=previous_byte_size,
        previous_mtime=previous_mtime,
    )

    import_result = None
    reason = "unchanged"
    if changed:
        import_result = _import_binary_meter_source_in_transaction(
            session,
            config,
            write_to_monitoring=True,
        )
        reason = "new_source" if state is None else "file_changed"

    backfill_result = None
    raw_rows = _count_raw_rows(session, config.key)
    monitoring_rows = _count_monitoring_rows(session, config.source_name)
    if raw_rows > monitoring_rows:
        backfill_result = _backfill_binary_source_to_monitoring_in_transaction(
            session,
            config,
        )
        if not changed:
            reason = "monitoring_backfill"

    return BinaryMeterSourceSyncResult(
        config=config,
        changed=changed,
        reason=reason,
        byte_size=source_stat.st_size,
        previous_byte_size=None if previous_byte_size is None else int(previous_byte_size),
        source_mtime=source_mtime,
        previous_mtime=previous_mtime,
        import_result=import_result,
        backfill_result=backfill_result,
    )


def _log_binary_meter_sync_result(result: BinaryMeterSourceSyncResult) -> None:
    import_result = result.import_result
    backfill_result = result.backfill_result
    logger.info(
        (
            "BINARY ELEKTROMER SYNC | source_key=%s | source=%s | reason=%s | "
            "changed=%s | raw_inserted=%s | monitoring_import_rows=%s | "
            "monitoring_backfill_added=%s"
        ),
        result.config.key,
        result.config.source_name,
        result.reason,
        result.changed,
        0 if import_result is None else import_result.inserted_raw_measurements,
        0 if import_result is None else import_result.monitoring_rows,
        0 if backfill_result is None else backfill_result.monitoring_rows_added,
    )


def _import_binary_meter_source_in_transaction(
    session: Session,
    config: BinaryMeterFileConfig,
    *,
    write_to_monitoring: bool,
) -> BinaryMeterImportResult:
    source_path = config.file_path
    source_stat = source_path.stat()
    source_mtime = datetime.fromtimestamp(source_stat.st_mtime)
    previous_last_sample_index = _load_last_sample_index(session, config.key)
    start_sample_index = previous_last_sample_index + 1
    parsed = parse_binary_meter_file(config, start_sample_index=start_sample_index)
    inserted_raw = _insert_raw_measurements(
        session,
        parsed,
        source_byte_size=source_stat.st_size,
        source_mtime=source_mtime,
    )
    monitoring_rows = 0
    if write_to_monitoring and parsed.measurements:
        monitoring_result = import_measurements(
            session,
            config.source_name,
            build_delta_source_rows(parsed),
        )
        monitoring_rows = len(monitoring_result.get("rows", []))

    new_last_sample_index = _resolve_new_last_sample_index(
        parsed,
        previous_last_sample_index=previous_last_sample_index,
    )
    _update_import_state(
        session,
        config=config,
        last_sample_index=new_last_sample_index,
        source_byte_size=source_stat.st_size,
        source_mtime=source_mtime,
        status="OK",
        error=None,
    )

    return BinaryMeterImportResult(
        config=config,
        byte_size=source_stat.st_size,
        previous_last_sample_index=previous_last_sample_index,
        new_last_sample_index=new_last_sample_index,
        parsed_sample_count=max(0, parsed.sample_count - start_sample_index),
        finite_measurements=parsed.finite_count,
        skipped_non_finite_count=parsed.skipped_non_finite_count,
        inserted_raw_measurements=inserted_raw,
        monitoring_rows=monitoring_rows,
    )


def _backfill_binary_source_to_monitoring_in_transaction(
    session: Session,
    config: BinaryMeterFileConfig,
) -> BinaryMeterMonitoringBackfillResult:
    monitoring_rows_before = _count_monitoring_rows(session, config.source_name)
    raw_rows = session.execute(
        text(
            """
            SELECT
                sample_index,
                identifikace,
                seriove_cislo,
                date,
                delta
            FROM dbo."Mereni_elektromery_BINARY"
            WHERE source_key = :source_key
            ORDER BY sample_index
            """
        ),
        {"source_key": config.key},
    ).mappings().all()
    monitoring_rows = build_delta_source_rows_from_raw_rows(config, raw_rows)
    prepared_monitoring_rows = 0
    for batch in chunked(monitoring_rows):
        result = import_measurements(session, config.source_name, batch)
        prepared_monitoring_rows += len(result.get("rows", []))

    monitoring_rows_after = _count_monitoring_rows(session, config.source_name)
    return BinaryMeterMonitoringBackfillResult(
        config=config,
        raw_rows=len(raw_rows),
        monitoring_rows_before=monitoring_rows_before,
        monitoring_rows_after=monitoring_rows_after,
        monitoring_rows_added=max(monitoring_rows_after - monitoring_rows_before, 0),
        prepared_monitoring_rows=prepared_monitoring_rows,
    )


def _config_to_db_params(config: BinaryMeterFileConfig) -> dict[str, object]:
    return {
        "source_key": config.key,
        "file_name": config.file_name,
        "identifikace": config.identifikace,
        "seriove_cislo": config.seriove_cislo,
        "first_timestamp": config.first_timestamp,
        "timestamp_offset_minutes": int(config.timestamp_offset.total_seconds() // 60),
        "interval_minutes": config.interval_minutes,
        "source_name": config.source_name,
        "double_format": config.double_format,
        "time_basis": config.time_basis,
        "source_timezone": config.source_timezone,
        "source_utc_offset_minutes": config.source_utc_offset_minutes,
        "timestamp_position": config.timestamp_position,
        "time_fold": config.time_fold,
    }


def _load_last_sample_index(session: Session, source_key: str) -> int:
    value = session.execute(
        text(
            """
            SELECT last_sample_index
            FROM dbo.elektromery_binary_import_state
            WHERE source_key = :source_key
            """
        ),
        {"source_key": source_key},
    ).scalar_one_or_none()
    if value is None:
        return -1
    return int(value)


def _load_import_state(session: Session, source_key: str):
    return session.execute(
        text(
            """
            SELECT
                last_sample_index,
                last_byte_size,
                last_mtime,
                last_imported_at,
                last_status,
                last_error
            FROM dbo.elektromery_binary_import_state
            WHERE source_key = :source_key
            """
        ),
        {"source_key": source_key},
    ).mappings().one_or_none()


def _count_raw_rows(session: Session, source_key: str) -> int:
    value = session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM dbo."Mereni_elektromery_BINARY"
            WHERE source_key = :source_key
            """
        ),
        {"source_key": source_key},
    ).scalar_one()
    return int(value or 0)


def _count_monitoring_rows(session: Session, source_name: str) -> int:
    value = session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM monitoring."Mereni_elektromery_vse"
            WHERE zdroj = :source_name
            """
        ),
        {"source_name": source_name},
    ).scalar_one()
    return int(value or 0)


def _insert_raw_measurements(
    session: Session,
    parsed: ParsedBinaryMeterFile,
    *,
    source_byte_size: int,
    source_mtime: datetime,
) -> int:
    rows = [
        {
            "source_key": parsed.config.key,
            "sample_index": measurement.sample_index,
            "identifikace": parsed.config.identifikace,
            "seriove_cislo": parsed.config.seriove_cislo,
            "date": measurement.date,
            **build_time_columns(
                measurement.date,
                parsed.config.source_name,
                _config_time_semantics_row(parsed.config),
            ),
            "delta": measurement.delta,
            "source_file": parsed.config.file_name,
            "source_byte_size": source_byte_size,
            "source_mtime": source_mtime,
        }
        for measurement in parsed.measurements
    ]
    if not rows:
        return 0

    inserted_count = 0
    statement = text(
        """
        INSERT INTO dbo."Mereni_elektromery_BINARY" (
            source_key,
            sample_index,
            identifikace,
            seriove_cislo,
            date,
            source_date,
            time_utc,
            time_basis,
            source_timezone,
            source_utc_offset_minutes,
            time_fold,
            timestamp_position,
            delta,
            source_file,
            source_byte_size,
            source_mtime
        )
        VALUES (
            :source_key,
            :sample_index,
            :identifikace,
            :seriove_cislo,
            :date,
            :source_date,
            :time_utc,
            :time_basis,
            :source_timezone,
            :source_utc_offset_minutes,
            :time_fold,
            :timestamp_position,
            :delta,
            :source_file,
            :source_byte_size,
            :source_mtime
        )
        ON CONFLICT (source_key, sample_index) DO NOTHING
        """
    )
    for batch in chunked(rows):
        result = session.execute(statement, batch)
        inserted_count += max(int(result.rowcount or 0), 0)
    return inserted_count


def _resolve_new_last_sample_index(
    parsed: ParsedBinaryMeterFile,
    *,
    previous_last_sample_index: int,
) -> int:
    if not parsed.measurements:
        return previous_last_sample_index
    return max(measurement.sample_index for measurement in parsed.measurements)


def _update_import_state(
    session: Session,
    *,
    config: BinaryMeterFileConfig,
    last_sample_index: int,
    source_byte_size: int,
    source_mtime: datetime,
    status: str,
    error: str | None,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO dbo.elektromery_binary_import_state (
                source_key,
                last_sample_index,
                last_byte_size,
                last_mtime,
                last_imported_at,
                last_status,
                last_error,
                updated_at
            )
            VALUES (
                :source_key,
                :last_sample_index,
                :last_byte_size,
                :last_mtime,
                now(),
                :last_status,
                :last_error,
                now()
            )
            ON CONFLICT (source_key) DO UPDATE SET
                last_sample_index = EXCLUDED.last_sample_index,
                last_byte_size = EXCLUDED.last_byte_size,
                last_mtime = EXCLUDED.last_mtime,
                last_imported_at = EXCLUDED.last_imported_at,
                last_status = EXCLUDED.last_status,
                last_error = EXCLUDED.last_error,
                updated_at = now()
            """
        ),
        {
            "source_key": config.key,
            "last_sample_index": last_sample_index,
            "last_byte_size": source_byte_size,
            "last_mtime": source_mtime,
            "last_status": status,
            "last_error": error,
        },
    )


def summarize_parsed_file(parsed: ParsedBinaryMeterFile) -> dict[str, object]:
    return {
        "key": parsed.config.key,
        "file_name": parsed.config.file_name,
        "identifikace": parsed.config.identifikace,
        "seriove_cislo": parsed.config.seriove_cislo,
        "source_name": parsed.config.source_name,
        "byte_size": parsed.byte_size,
        "sample_count": parsed.sample_count,
        "finite_count": parsed.finite_count,
        "skipped_non_finite_count": parsed.skipped_non_finite_count,
        "negative_count": parsed.negative_count,
        "positive_count": parsed.positive_count,
        "zero_count": parsed.zero_count,
        "first_timestamp": parsed.first_timestamp,
        "last_timestamp": parsed.last_timestamp,
        "first_measurement_timestamp": parsed.first_measurement_timestamp,
        "last_measurement_timestamp": parsed.last_measurement_timestamp,
        "min_delta": parsed.min_delta,
        "max_delta": parsed.max_delta,
        "total_delta": parsed.total_delta,
    }
