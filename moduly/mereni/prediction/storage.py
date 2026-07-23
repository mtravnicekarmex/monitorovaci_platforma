from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from moduly.mereni.prediction.contracts import (
    PredictionForecastPeriod,
    PredictionMetricSummary,
    PredictionSelectedModelDecision,
)


SELECTION_MODE_DRY_RUN = "dry_run"
SELECTION_MODE_ACTIVE = "active"
ARCHIVE_SOURCE_WEEKLY_REBUILD = "weekly_rebuild"
ARCHIVE_SOURCE_HISTORICAL_BACKFILL = "historical_backfill"
SUPPORTED_SELECTION_MODES = frozenset(
    {
        SELECTION_MODE_DRY_RUN,
        SELECTION_MODE_ACTIVE,
    }
)
SUPPORTED_ARCHIVE_SOURCES = frozenset(
    {
        ARCHIVE_SOURCE_WEEKLY_REBUILD,
        ARCHIVE_SOURCE_HISTORICAL_BACKFILL,
    }
)

SNAPSHOT_IDENTITY_COLUMNS = (
    "medium_key",
    "identifier",
    "forecast_period_start",
    "forecast_period_end",
    "forecast_cadence",
    "selection_mode",
)

PROFILE_SNAPSHOT_IDENTITY_COLUMNS = (
    "medium_key",
    "identifier",
    "forecast_period_start",
    "forecast_period_end",
    "forecast_cadence",
    "archive_source",
    "archive_version",
    "selection_mode",
    "interval_minutes",
    "day_of_week",
    "slot",
)

BACKFILL_CANDIDATE_METRIC_IDENTITY_COLUMNS = (
    "medium_key",
    "identifier",
    "forecast_period_start",
    "forecast_period_end",
    "forecast_cadence",
    "archive_version",
    "model_version",
)


class Base(DeclarativeBase):
    pass


class PredictionSelectedModelSnapshot(Base):
    __tablename__ = "prediction_selected_model_snapshots"
    __table_args__ = (
        UniqueConstraint(
            *SNAPSHOT_IDENTITY_COLUMNS,
            name="uq_prediction_selected_model_snapshots_identity",
        ),
        Index(
            "ix_prediction_selected_model_snapshots_lookup",
            "medium_key",
            "identifier",
            "forecast_period_start",
            "forecast_period_end",
            "selection_mode",
        ),
        Index(
            "ix_prediction_selected_model_snapshots_period",
            "medium_key",
            "forecast_period_start",
            "forecast_period_end",
        ),
        Index(
            "ix_prediction_selected_model_snapshots_run",
            "medium_key",
            "selection_run_id",
        ),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    medium_key: Mapped[str] = mapped_column(String(40), nullable=False)
    identifier: Mapped[str] = mapped_column(String(250), nullable=False)
    forecast_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
    )
    forecast_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
    )
    forecast_cadence: Mapped[str] = mapped_column(String(20), nullable=False)
    forecast_period_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    selection_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    selection_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_model_key: Mapped[str] = mapped_column(String(80), nullable=False)
    selected_model_name: Mapped[str] = mapped_column(String(150), nullable=False)
    global_model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    global_model_key: Mapped[str] = mapped_column(String(80), nullable=False)
    global_model_name: Mapped[str] = mapped_column(String(150), nullable=False)
    fallback_reason: Mapped[str] = mapped_column(String(80), nullable=False)
    uses_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validation_total_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_validation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    rmse: Mapped[float | None] = mapped_column(Float, nullable=True)
    bias: Mapped[float | None] = mapped_column(Float, nullable=True)
    wape: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        nullable=False,
    )


class PredictionProfileSnapshot(Base):
    __tablename__ = "prediction_profile_snapshots"
    __table_args__ = (
        UniqueConstraint(
            *PROFILE_SNAPSHOT_IDENTITY_COLUMNS,
            name="uq_prediction_profile_snapshots_identity",
        ),
        Index(
            "ix_prediction_profile_snapshots_lookup",
            "medium_key",
            "identifier",
            "forecast_period_start",
            "forecast_period_end",
            "selection_mode",
        ),
        Index(
            "ix_prediction_profile_snapshots_period",
            "medium_key",
            "forecast_period_start",
            "forecast_period_end",
        ),
        Index(
            "ix_prediction_profile_snapshots_archive_run",
            "archive_source",
            "archive_version",
            "archive_run_id",
        ),
        Index(
            "ix_prediction_profile_snapshots_selection_run",
            "medium_key",
            "selection_run_id",
        ),
        Index(
            "ix_prediction_profile_snapshots_created",
            "created_at",
        ),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    medium_key: Mapped[str] = mapped_column(String(40), nullable=False)
    identifier: Mapped[str] = mapped_column(String(250), nullable=False)
    forecast_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
    )
    forecast_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
    )
    forecast_cadence: Mapped[str] = mapped_column(String(20), nullable=False)
    forecast_period_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    archive_source: Mapped[str] = mapped_column(String(40), nullable=False)
    archive_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    selection_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    selection_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archive_run_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    global_model_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    global_model_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    global_model_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    uses_fallback: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    fallback_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_mean: Mapped[float] = mapped_column(Float, nullable=False)
    expected_median: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_p10: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_p90: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_profile_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    training_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    training_window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    validation_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    validation_window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        nullable=False,
    )


class PredictionBackfillCandidateMetric(Base):
    __tablename__ = "prediction_backfill_candidate_metrics"
    __table_args__ = (
        UniqueConstraint(
            *BACKFILL_CANDIDATE_METRIC_IDENTITY_COLUMNS,
            name="uq_prediction_backfill_candidate_metrics_identity",
        ),
        Index(
            "ix_prediction_backfill_candidate_metrics_lookup",
            "medium_key",
            "identifier",
            "forecast_period_start",
            "forecast_period_end",
        ),
        Index(
            "ix_prediction_backfill_candidate_metrics_period",
            "medium_key",
            "forecast_period_start",
            "forecast_period_end",
        ),
        Index(
            "ix_prediction_backfill_candidate_metrics_run",
            "archive_version",
            "archive_run_id",
        ),
        Index(
            "ix_prediction_backfill_candidate_metrics_selected",
            "medium_key",
            "model_version",
            "selected",
        ),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    medium_key: Mapped[str] = mapped_column(String(40), nullable=False)
    identifier: Mapped[str] = mapped_column(String(250), nullable=False)
    forecast_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
    )
    forecast_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
    )
    forecast_cadence: Mapped[str] = mapped_column(String(20), nullable=False)
    forecast_period_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    archive_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    archive_run_id: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_key: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(150), nullable=False)
    selection_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rank_by_policy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    validation_total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_validation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    coverage: Mapped[float] = mapped_column(Float, nullable=False)
    mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    rmse: Mapped[float | None] = mapped_column(Float, nullable=True)
    bias: Mapped[float | None] = mapped_column(Float, nullable=True)
    wape: Mapped[float | None] = mapped_column(Float, nullable=True)
    training_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    training_window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    validation_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    validation_window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        nullable=False,
    )


def ensure_prediction_selected_model_snapshot_table(*, engine=None) -> None:
    if engine is None:
        from core.db.connect import ENGINE_PG

        engine = ENGINE_PG

    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        PredictionSelectedModelSnapshot.__table__.create(bind=conn, checkfirst=True)
        conn.execute(
            text(
                """
                ALTER TABLE monitoring.prediction_selected_model_snapshots
                    ADD COLUMN IF NOT EXISTS forecast_period_label varchar(80),
                    ADD COLUMN IF NOT EXISTS selection_mode varchar(20) NOT NULL DEFAULT 'dry_run',
                    ADD COLUMN IF NOT EXISTS global_model_key varchar(80) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS fallback_reason varchar(80) NOT NULL DEFAULT 'none',
                    ADD COLUMN IF NOT EXISTS uses_fallback boolean NOT NULL DEFAULT false,
                    ADD COLUMN IF NOT EXISTS validation_total_count integer,
                    ADD COLUMN IF NOT EXISTS matched_validation_count integer,
                    ADD COLUMN IF NOT EXISTS coverage double precision,
                    ADD COLUMN IF NOT EXISTS mae double precision,
                    ADD COLUMN IF NOT EXISTS rmse double precision,
                    ADD COLUMN IF NOT EXISTS bias double precision,
                    ADD COLUMN IF NOT EXISTS wape double precision,
                    ADD COLUMN IF NOT EXISTS metadata_json text
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_prediction_selected_model_snapshots_identity
                ON monitoring.prediction_selected_model_snapshots
                    (medium_key, identifier, forecast_period_start, forecast_period_end,
                     forecast_cadence, selection_mode)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_prediction_selected_model_snapshots_lookup
                ON monitoring.prediction_selected_model_snapshots
                    (medium_key, identifier, forecast_period_start, forecast_period_end,
                     selection_mode)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_prediction_selected_model_snapshots_period
                ON monitoring.prediction_selected_model_snapshots
                    (medium_key, forecast_period_start, forecast_period_end)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_prediction_selected_model_snapshots_run
                ON monitoring.prediction_selected_model_snapshots
                    (medium_key, selection_run_id)
                """
            )
        )


def ensure_prediction_profile_snapshot_table(*, engine=None) -> None:
    if engine is None:
        from core.db.connect import ENGINE_PG

        engine = ENGINE_PG

    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        PredictionProfileSnapshot.__table__.create(bind=conn, checkfirst=True)
        conn.execute(
            text(
                """
                ALTER TABLE monitoring.prediction_profile_snapshots
                    ADD COLUMN IF NOT EXISTS forecast_period_label varchar(80),
                    ADD COLUMN IF NOT EXISTS archive_source varchar(40) NOT NULL DEFAULT 'weekly_rebuild',
                    ADD COLUMN IF NOT EXISTS archive_version integer NOT NULL DEFAULT 1,
                    ADD COLUMN IF NOT EXISTS selection_mode varchar(20) NOT NULL DEFAULT 'active',
                    ADD COLUMN IF NOT EXISTS selection_run_id integer,
                    ADD COLUMN IF NOT EXISTS archive_run_id varchar(80) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS model_key varchar(80) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS model_name varchar(150) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS global_model_version integer,
                    ADD COLUMN IF NOT EXISTS global_model_key varchar(80),
                    ADD COLUMN IF NOT EXISTS global_model_name varchar(150),
                    ADD COLUMN IF NOT EXISTS uses_fallback boolean NOT NULL DEFAULT false,
                    ADD COLUMN IF NOT EXISTS fallback_reason varchar(80),
                    ADD COLUMN IF NOT EXISTS expected_median double precision,
                    ADD COLUMN IF NOT EXISTS expected_p10 double precision,
                    ADD COLUMN IF NOT EXISTS expected_p90 double precision,
                    ADD COLUMN IF NOT EXISTS expected_std double precision,
                    ADD COLUMN IF NOT EXISTS sample_size integer,
                    ADD COLUMN IF NOT EXISTS source_profile_created_at timestamp without time zone,
                    ADD COLUMN IF NOT EXISTS training_window_start timestamp without time zone,
                    ADD COLUMN IF NOT EXISTS training_window_end timestamp without time zone,
                    ADD COLUMN IF NOT EXISTS validation_window_start timestamp without time zone,
                    ADD COLUMN IF NOT EXISTS validation_window_end timestamp without time zone,
                    ADD COLUMN IF NOT EXISTS metadata_json text
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_prediction_profile_snapshots_identity
                ON monitoring.prediction_profile_snapshots
                    (medium_key, identifier, forecast_period_start, forecast_period_end,
                     forecast_cadence, archive_source, archive_version, selection_mode,
                     interval_minutes, day_of_week, slot)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_prediction_profile_snapshots_lookup
                ON monitoring.prediction_profile_snapshots
                    (medium_key, identifier, forecast_period_start, forecast_period_end,
                     selection_mode)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_prediction_profile_snapshots_period
                ON monitoring.prediction_profile_snapshots
                    (medium_key, forecast_period_start, forecast_period_end)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_prediction_profile_snapshots_archive_run
                ON monitoring.prediction_profile_snapshots
                    (archive_source, archive_version, archive_run_id)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_prediction_profile_snapshots_selection_run
                ON monitoring.prediction_profile_snapshots
                    (medium_key, selection_run_id)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_prediction_profile_snapshots_created
                ON monitoring.prediction_profile_snapshots (created_at)
                """
            )
        )


def ensure_prediction_backfill_candidate_metric_table(*, engine=None) -> None:
    if engine is None:
        from core.db.connect import ENGINE_PG

        engine = ENGINE_PG

    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        PredictionBackfillCandidateMetric.__table__.create(bind=conn, checkfirst=True)
        conn.execute(
            text(
                """
                ALTER TABLE monitoring.prediction_backfill_candidate_metrics
                    ADD COLUMN IF NOT EXISTS forecast_period_label varchar(80),
                    ADD COLUMN IF NOT EXISTS archive_version integer NOT NULL DEFAULT 1,
                    ADD COLUMN IF NOT EXISTS archive_run_id varchar(80),
                    ADD COLUMN IF NOT EXISTS model_key varchar(80),
                    ADD COLUMN IF NOT EXISTS model_name varchar(150),
                    ADD COLUMN IF NOT EXISTS selection_enabled boolean NOT NULL DEFAULT true,
                    ADD COLUMN IF NOT EXISTS selected boolean NOT NULL DEFAULT false,
                    ADD COLUMN IF NOT EXISTS eligible boolean NOT NULL DEFAULT true,
                    ADD COLUMN IF NOT EXISTS rank_by_policy integer,
                    ADD COLUMN IF NOT EXISTS fallback_reason varchar(80),
                    ADD COLUMN IF NOT EXISTS validation_total_count integer NOT NULL DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS matched_validation_count integer NOT NULL DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS coverage double precision NOT NULL DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS mae double precision,
                    ADD COLUMN IF NOT EXISTS rmse double precision,
                    ADD COLUMN IF NOT EXISTS bias double precision,
                    ADD COLUMN IF NOT EXISTS wape double precision,
                    ADD COLUMN IF NOT EXISTS training_window_start timestamp without time zone,
                    ADD COLUMN IF NOT EXISTS training_window_end timestamp without time zone,
                    ADD COLUMN IF NOT EXISTS validation_window_start timestamp without time zone,
                    ADD COLUMN IF NOT EXISTS validation_window_end timestamp without time zone,
                    ADD COLUMN IF NOT EXISTS metadata_json text
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_prediction_backfill_candidate_metrics_identity
                ON monitoring.prediction_backfill_candidate_metrics
                    (medium_key, identifier, forecast_period_start, forecast_period_end,
                     forecast_cadence, archive_version, model_version)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_prediction_backfill_candidate_metrics_lookup
                ON monitoring.prediction_backfill_candidate_metrics
                    (medium_key, identifier, forecast_period_start, forecast_period_end)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_prediction_backfill_candidate_metrics_period
                ON monitoring.prediction_backfill_candidate_metrics
                    (medium_key, forecast_period_start, forecast_period_end)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_prediction_backfill_candidate_metrics_run
                ON monitoring.prediction_backfill_candidate_metrics
                    (archive_version, archive_run_id)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_prediction_backfill_candidate_metrics_selected
                ON monitoring.prediction_backfill_candidate_metrics
                    (medium_key, model_version, selected)
                """
            )
        )


def normalize_selection_mode(selection_mode: str) -> str:
    normalized = str(selection_mode).strip().lower()
    if normalized not in SUPPORTED_SELECTION_MODES:
        raise ValueError(f"Unsupported prediction selection mode: {selection_mode!r}")
    return normalized


def normalize_archive_source(archive_source: str) -> str:
    normalized = str(archive_source).strip().lower()
    if normalized not in SUPPORTED_ARCHIVE_SOURCES:
        raise ValueError(f"Unsupported prediction archive source: {archive_source!r}")
    return normalized


def decision_to_selected_model_snapshot_row(
    decision: PredictionSelectedModelDecision,
    *,
    selection_mode: str = SELECTION_MODE_DRY_RUN,
) -> dict[str, object]:
    metrics = decision.metrics
    row: dict[str, object] = {
        "medium_key": decision.medium_key,
        "identifier": decision.identifier,
        "forecast_period_start": decision.forecast_period.start,
        "forecast_period_end": decision.forecast_period.end,
        "forecast_cadence": decision.forecast_period.cadence.value,
        "forecast_period_label": decision.forecast_period.label,
        "selection_mode": normalize_selection_mode(selection_mode),
        "selection_run_id": decision.selection_run_id,
        "selected_model_version": decision.selected_model_version,
        "selected_model_key": decision.selected_model_key,
        "selected_model_name": decision.selected_model_name,
        "global_model_version": decision.global_model_version,
        "global_model_key": decision.global_model_key,
        "global_model_name": decision.global_model_name,
        "fallback_reason": decision.fallback_reason.value,
        "uses_fallback": decision.uses_fallback,
        "validation_total_count": None if metrics is None else metrics.validation_total_count,
        "matched_validation_count": None if metrics is None else metrics.matched_validation_count,
        "coverage": None if metrics is None else metrics.coverage,
        "mae": None if metrics is None else metrics.mae,
        "rmse": None if metrics is None else metrics.rmse,
        "bias": None if metrics is None else metrics.bias,
        "wape": None if metrics is None else metrics.wape,
        "metadata_json": _metadata_to_json(decision.metadata),
        "created_at": decision.created_at or _utc_now_naive(),
    }
    return row


def build_insert_selected_model_snapshots_statement(
    rows: Sequence[Mapping[str, object]],
):
    statement = postgresql_insert(PredictionSelectedModelSnapshot).values(list(rows))
    return statement.on_conflict_do_nothing(
        index_elements=list(SNAPSHOT_IDENTITY_COLUMNS),
    )


def build_insert_prediction_profile_snapshots_statement(
    rows: Sequence[Mapping[str, object]],
):
    statement = postgresql_insert(PredictionProfileSnapshot).values(list(rows))
    return statement.on_conflict_do_nothing(
        index_elements=list(PROFILE_SNAPSHOT_IDENTITY_COLUMNS),
    )


def build_insert_prediction_backfill_candidate_metrics_statement(
    rows: Sequence[Mapping[str, object]],
):
    statement = postgresql_insert(PredictionBackfillCandidateMetric).values(list(rows))
    return statement.on_conflict_do_nothing(
        index_elements=list(BACKFILL_CANDIDATE_METRIC_IDENTITY_COLUMNS),
    )


def persist_prediction_profile_snapshots(
    session,
    rows: Sequence[Mapping[str, object]],
) -> int:
    if not rows:
        return 0

    result = session.execute(build_insert_prediction_profile_snapshots_statement(rows))
    rowcount = getattr(result, "rowcount", None)
    if rowcount is None or rowcount < 0:
        return 0
    return int(rowcount)


def persist_prediction_backfill_candidate_metrics(
    session,
    rows: Sequence[Mapping[str, object]],
) -> int:
    if not rows:
        return 0

    result = session.execute(
        build_insert_prediction_backfill_candidate_metrics_statement(rows)
    )
    rowcount = getattr(result, "rowcount", None)
    if rowcount is None or rowcount < 0:
        return 0
    return int(rowcount)


def persist_selected_model_decisions(
    session,
    decisions: Sequence[PredictionSelectedModelDecision],
    *,
    selection_mode: str = SELECTION_MODE_DRY_RUN,
) -> int:
    rows = [
        decision_to_selected_model_snapshot_row(
            decision,
            selection_mode=selection_mode,
        )
        for decision in decisions
    ]
    if not rows:
        return 0

    result = session.execute(build_insert_selected_model_snapshots_statement(rows))
    rowcount = getattr(result, "rowcount", None)
    if rowcount is None or rowcount < 0:
        return 0
    return int(rowcount)


def build_selected_model_snapshot_lookup_statement(
    *,
    medium_key: str,
    identifier: str,
    forecast_period: PredictionForecastPeriod,
    selection_mode: str = SELECTION_MODE_ACTIVE,
):
    snapshot = PredictionSelectedModelSnapshot
    return (
        select(
            snapshot.medium_key,
            snapshot.identifier,
            snapshot.forecast_period_start,
            snapshot.forecast_period_end,
            snapshot.forecast_cadence,
            snapshot.forecast_period_label,
            snapshot.selection_run_id,
            snapshot.selected_model_version,
            snapshot.selected_model_key,
            snapshot.selected_model_name,
            snapshot.global_model_version,
            snapshot.global_model_key,
            snapshot.global_model_name,
            snapshot.fallback_reason,
            snapshot.validation_total_count,
            snapshot.matched_validation_count,
            snapshot.coverage,
            snapshot.mae,
            snapshot.rmse,
            snapshot.bias,
            snapshot.wape,
            snapshot.metadata_json,
            snapshot.created_at,
        )
        .where(
            snapshot.medium_key == medium_key,
            snapshot.identifier == identifier,
            snapshot.forecast_period_start == forecast_period.start,
            snapshot.forecast_period_end == forecast_period.end,
            snapshot.forecast_cadence == forecast_period.cadence.value,
            snapshot.selection_mode == normalize_selection_mode(selection_mode),
        )
        .limit(1)
    )


def load_selected_model_decision(
    session,
    *,
    medium_key: str,
    identifier: str,
    forecast_period: PredictionForecastPeriod,
    selection_mode: str = SELECTION_MODE_ACTIVE,
) -> PredictionSelectedModelDecision | None:
    row = (
        session.execute(
            build_selected_model_snapshot_lookup_statement(
                medium_key=medium_key,
                identifier=identifier,
                forecast_period=forecast_period,
                selection_mode=selection_mode,
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return selected_model_snapshot_row_to_decision(row)


def selected_model_snapshot_row_to_decision(
    row: Mapping[str, Any],
) -> PredictionSelectedModelDecision:
    metrics = _metrics_from_row(row)
    return PredictionSelectedModelDecision(
        medium_key=str(row["medium_key"]),
        identifier=str(row["identifier"]),
        forecast_period=PredictionForecastPeriod(
            start=row["forecast_period_start"],
            end=row["forecast_period_end"],
            cadence=row["forecast_cadence"],
            label=row.get("forecast_period_label"),
        ),
        selection_run_id=(
            None
            if row.get("selection_run_id") is None
            else int(row["selection_run_id"])
        ),
        selected_model_version=int(row["selected_model_version"]),
        selected_model_key=str(row["selected_model_key"]),
        selected_model_name=str(row["selected_model_name"]),
        global_model_version=int(row["global_model_version"]),
        global_model_key=str(row["global_model_key"]),
        global_model_name=str(row["global_model_name"]),
        fallback_reason=str(row["fallback_reason"]),
        metrics=metrics,
        created_at=row.get("created_at"),
        metadata=_metadata_from_json(row.get("metadata_json")),
    )


def _metrics_from_row(row: Mapping[str, Any]) -> PredictionMetricSummary | None:
    validation_total_count = row.get("validation_total_count")
    if validation_total_count is None:
        return None
    return PredictionMetricSummary(
        validation_total_count=int(validation_total_count),
        matched_validation_count=int(row.get("matched_validation_count") or 0),
        coverage=float(row.get("coverage") or 0.0),
        mae=None if row.get("mae") is None else float(row["mae"]),
        rmse=None if row.get("rmse") is None else float(row["rmse"]),
        bias=None if row.get("bias") is None else float(row["bias"]),
        wape=None if row.get("wape") is None else float(row["wape"]),
    )


def _metadata_to_json(metadata: Mapping[str, Any]) -> str | None:
    if not metadata:
        return None
    return json.dumps(dict(metadata), ensure_ascii=False, sort_keys=True)


def _metadata_from_json(value: object) -> Mapping[str, Any]:
    if not value:
        return {}
    if not isinstance(value, str):
        return {}
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        return {}
    return decoded


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
