from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from core.db.connect import get_session_pg
from moduly.mereni.elektromery.elektromery_prediction import (
    ELEKTROMERY_PIPELINE_SETTINGS,
    get_candidate_model_specs as get_elektromery_candidate_model_specs,
)
from moduly.mereni.plynomery.plynomery_prediction import (
    PLYNOMERY_PIPELINE_SETTINGS,
    get_candidate_model_specs as get_plynomery_candidate_model_specs,
)
from moduly.mereni.prediction import PredictionCandidateSpec, PredictionPipelineSettings
from moduly.mereni.vodomery.vodomery_prediction import (
    VODOMERY_PIPELINE_SETTINGS,
    get_candidate_model_specs as get_vodomery_candidate_model_specs,
)
from services.api.schemas.prediction import (
    PredictionCandidateCatalogRecord,
    PredictionCandidatePerformanceRecord,
    PredictionDistributionRecord,
    PredictionIdentifierSelectionRecord,
    PredictionMediumPerformance,
    PredictionPerformanceResponse,
    PredictionSelectionRunRecord,
    PredictionSnapshotSummary,
)


SNAPSHOT_TABLE = "monitoring.prediction_selected_model_snapshots"
WORST_IDENTIFIER_LIMIT = 25


@dataclass(frozen=True)
class PredictionMediumConfig:
    medium_key: str
    medium_label: str
    settings: PredictionPipelineSettings
    specs_loader: Callable[[], tuple[PredictionCandidateSpec, ...]]
    selection_run_table: str | None = None
    candidate_table: str | None = None
    candidate_table_shape: str | None = None


MEDIA_CONFIGS: tuple[PredictionMediumConfig, ...] = (
    PredictionMediumConfig(
        medium_key="vodomery",
        medium_label="Vodomery",
        settings=VODOMERY_PIPELINE_SETTINGS,
        specs_loader=get_vodomery_candidate_model_specs,
        selection_run_table="monitoring.vodomery_model_selection_runs",
        candidate_table="monitoring.vodomery_model_selection_candidates",
        candidate_table_shape="vodomery",
    ),
    PredictionMediumConfig(
        medium_key="plynomery",
        medium_label="Plynomery",
        settings=PLYNOMERY_PIPELINE_SETTINGS,
        specs_loader=get_plynomery_candidate_model_specs,
        selection_run_table="monitoring.plynomery_model_selection_runs",
        candidate_table="monitoring.plynomery_model_selection_candidates",
        candidate_table_shape="plynomery",
    ),
    PredictionMediumConfig(
        medium_key="elektromery",
        medium_label="Elektromery",
        settings=ELEKTROMERY_PIPELINE_SETTINGS,
        specs_loader=get_elektromery_candidate_model_specs,
    ),
)


def collect_prediction_performance_report(
    *,
    session_factory: Callable[[], object] = get_session_pg,
    reference_time: datetime | None = None,
) -> PredictionPerformanceResponse:
    checked_at = reference_time or datetime.now()
    session = session_factory()
    try:
        media_reports = [
            _collect_medium_performance(session, config)
            for config in MEDIA_CONFIGS
        ]
    finally:
        session.close()

    status = "error" if any(item.status == "error" for item in media_reports) else "ok"
    return PredictionPerformanceResponse(
        status=status,
        checked_at=checked_at,
        media=media_reports,
    )


def _collect_medium_performance(
    session,
    config: PredictionMediumConfig,
) -> PredictionMediumPerformance:
    catalog = _build_candidate_catalog(config)
    catalog_by_version = {row.model_version: row for row in catalog}

    try:
        if config.selection_run_table is None or config.candidate_table is None:
            return PredictionMediumPerformance(
                medium_key=config.medium_key,
                medium_label=config.medium_label,
                forecast_cadence=_forecast_cadence(config),
                status="not_run",
                detail="Candidate models are registered, but no persisted selection run is enabled for this medium yet.",
                candidate_catalog=catalog,
                snapshot_summary=_load_latest_snapshot_summary(session, config),
                worst_identifier_selections=_load_worst_identifier_selections(session, config),
            )

        if not _table_exists(session, config.selection_run_table):
            return PredictionMediumPerformance(
                medium_key=config.medium_key,
                medium_label=config.medium_label,
                forecast_cadence=_forecast_cadence(config),
                status="not_run",
                detail=f"Selection run table {config.selection_run_table} is not present.",
                candidate_catalog=catalog,
                snapshot_summary=_load_latest_snapshot_summary(session, config),
                worst_identifier_selections=_load_worst_identifier_selections(session, config),
            )

        run = _load_latest_selection_run(session, config)
        if run is None:
            return PredictionMediumPerformance(
                medium_key=config.medium_key,
                medium_label=config.medium_label,
                forecast_cadence=_forecast_cadence(config),
                status="not_run",
                detail="No persisted selection run was found.",
                candidate_catalog=catalog,
                snapshot_summary=_load_latest_snapshot_summary(session, config),
                worst_identifier_selections=_load_worst_identifier_selections(session, config),
            )

        candidates = (
            _load_candidate_performance(session, config, run.selection_run_id, catalog_by_version)
            if _table_exists(session, config.candidate_table)
            else []
        )
        return PredictionMediumPerformance(
            medium_key=config.medium_key,
            medium_label=config.medium_label,
            forecast_cadence=_forecast_cadence(config),
            status="ok",
            detail="Latest selection run loaded.",
            candidate_catalog=catalog,
            latest_selection_run=run,
            candidate_performance=candidates,
            snapshot_summary=_load_latest_snapshot_summary(session, config),
            worst_identifier_selections=_load_worst_identifier_selections(session, config),
        )
    except SQLAlchemyError as exc:
        return PredictionMediumPerformance(
            medium_key=config.medium_key,
            medium_label=config.medium_label,
            forecast_cadence=_forecast_cadence(config),
            status="error",
            detail=f"Prediction performance query failed: {type(exc).__name__}",
            candidate_catalog=catalog,
        )


def _build_candidate_catalog(
    config: PredictionMediumConfig,
) -> list[PredictionCandidateCatalogRecord]:
    return [
        PredictionCandidateCatalogRecord(
            medium_key=config.medium_key,
            medium_label=config.medium_label,
            forecast_cadence=_forecast_cadence(config),
            model_version=spec.model_version,
            model_key=spec.model_key,
            model_name=spec.model_name,
            training_window_months=spec.training_window_months,
            validation_window_months=spec.validation_window_months,
            selection_enabled=spec.selection_enabled,
        )
        for spec in config.specs_loader()
    ]


def _forecast_cadence(config: PredictionMediumConfig) -> str:
    return config.settings.forecast_period_definition.cadence.value


def _table_exists(session, table_name: str) -> bool:
    return bool(
        session.execute(
            text("SELECT to_regclass(:table_name) IS NOT NULL AS table_present"),
            {"table_name": table_name},
        ).scalar()
    )


def _load_latest_selection_run(
    session,
    config: PredictionMediumConfig,
) -> PredictionSelectionRunRecord | None:
    if config.selection_run_table is None:
        return None

    row = (
        session.execute(
            text(
                f"""
                /* prediction_performance:latest_run:{config.medium_key} */
                SELECT
                    id AS selection_run_id,
                    selected_model_version,
                    selected_model_name,
                    train_start,
                    train_end,
                    validation_start,
                    validation_end,
                    deploy_start,
                    deploy_end,
                    created_at
                FROM {config.selection_run_table}
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return PredictionSelectionRunRecord(
        medium_key=config.medium_key,
        selection_run_id=int(row["selection_run_id"]),
        selected_model_version=int(row["selected_model_version"]),
        selected_model_name=str(row["selected_model_name"]),
        train_start=row["train_start"],
        train_end=row["train_end"],
        validation_start=row["validation_start"],
        validation_end=row["validation_end"],
        deploy_start=row["deploy_start"],
        deploy_end=row["deploy_end"],
        created_at=row["created_at"],
    )


def _load_candidate_performance(
    session,
    config: PredictionMediumConfig,
    selection_run_id: int,
    catalog_by_version: Mapping[int, PredictionCandidateCatalogRecord],
) -> list[PredictionCandidatePerformanceRecord]:
    if config.candidate_table_shape == "vodomery":
        rows = _load_vodomery_candidate_rows(session, config, selection_run_id)
    elif config.candidate_table_shape == "plynomery":
        rows = _load_plynomery_candidate_rows(session, config, selection_run_id)
    else:
        rows = []

    return [
        _candidate_row_to_record(
            row,
            config=config,
            catalog_by_version=catalog_by_version,
        )
        for row in rows
    ]


def _load_vodomery_candidate_rows(
    session,
    config: PredictionMediumConfig,
    selection_run_id: int,
) -> Sequence[Mapping[str, object]]:
    return (
        session.execute(
            text(
                f"""
                /* prediction_performance:candidates:{config.medium_key} */
                SELECT
                    selection_run_id,
                    model_version,
                    model_key,
                    model_name,
                    training_window_months,
                    validation_window_months,
                    selection_enabled,
                    selected,
                    validation_total_count,
                    matched_validation_count,
                    coverage,
                    mae,
                    rmse,
                    bias,
                    NULL::double precision AS wape,
                    rolling_backtest_fold_count,
                    rolling_validation_total_count,
                    rolling_matched_validation_count,
                    rolling_coverage,
                    rolling_mae,
                    rolling_rmse,
                    rolling_bias,
                    rolling_wape,
                    profile_count,
                    created_at
                FROM {config.candidate_table}
                WHERE selection_run_id = :selection_run_id
                ORDER BY model_version
                """
            ),
            {"selection_run_id": selection_run_id},
        )
        .mappings()
        .all()
    )


def _load_plynomery_candidate_rows(
    session,
    config: PredictionMediumConfig,
    selection_run_id: int,
) -> Sequence[Mapping[str, object]]:
    return (
        session.execute(
            text(
                f"""
                /* prediction_performance:candidates:{config.medium_key} */
                SELECT
                    selection_run_id,
                    model_version,
                    NULL::varchar AS model_key,
                    model_name,
                    NULL::integer AS training_window_months,
                    NULL::integer AS validation_window_months,
                    TRUE AS selection_enabled,
                    selected,
                    validation_total_count,
                    matched_validation_count,
                    coverage,
                    mae,
                    rmse,
                    bias,
                    NULL::double precision AS wape,
                    0 AS rolling_backtest_fold_count,
                    NULL::integer AS rolling_validation_total_count,
                    NULL::integer AS rolling_matched_validation_count,
                    NULL::double precision AS rolling_coverage,
                    NULL::double precision AS rolling_mae,
                    NULL::double precision AS rolling_rmse,
                    NULL::double precision AS rolling_bias,
                    NULL::double precision AS rolling_wape,
                    profile_count,
                    created_at
                FROM {config.candidate_table}
                WHERE selection_run_id = :selection_run_id
                ORDER BY model_version
                """
            ),
            {"selection_run_id": selection_run_id},
        )
        .mappings()
        .all()
    )


def _candidate_row_to_record(
    row: Mapping[str, object],
    *,
    config: PredictionMediumConfig,
    catalog_by_version: Mapping[int, PredictionCandidateCatalogRecord],
) -> PredictionCandidatePerformanceRecord:
    model_version = int(row["model_version"])
    catalog = catalog_by_version.get(model_version)
    return PredictionCandidatePerformanceRecord(
        medium_key=config.medium_key,
        medium_label=config.medium_label,
        selection_run_id=int(row["selection_run_id"]),
        model_version=model_version,
        model_key=str(row.get("model_key") or (catalog.model_key if catalog else f"model_{model_version}")),
        model_name=str(row.get("model_name") or (catalog.model_name if catalog else f"Model {model_version}")),
        training_window_months=_int_or_none(
            row.get("training_window_months")
            if row.get("training_window_months") is not None
            else (catalog.training_window_months if catalog else None)
        ),
        validation_window_months=_int_or_none(
            row.get("validation_window_months")
            if row.get("validation_window_months") is not None
            else (catalog.validation_window_months if catalog else None)
        ),
        selection_enabled=bool(
            row.get("selection_enabled")
            if row.get("selection_enabled") is not None
            else (catalog.selection_enabled if catalog else True)
        ),
        selected=bool(row.get("selected")),
        validation_total_count=int(row.get("validation_total_count") or 0),
        matched_validation_count=int(row.get("matched_validation_count") or 0),
        coverage=float(row.get("coverage") or 0.0),
        mae=_float_or_none(row.get("mae")),
        rmse=_float_or_none(row.get("rmse")),
        bias=_float_or_none(row.get("bias")),
        wape=_float_or_none(row.get("wape")),
        rolling_backtest_fold_count=int(row.get("rolling_backtest_fold_count") or 0),
        rolling_validation_total_count=_int_or_none(row.get("rolling_validation_total_count")),
        rolling_matched_validation_count=_int_or_none(row.get("rolling_matched_validation_count")),
        rolling_coverage=_float_or_none(row.get("rolling_coverage")),
        rolling_mae=_float_or_none(row.get("rolling_mae")),
        rolling_rmse=_float_or_none(row.get("rolling_rmse")),
        rolling_bias=_float_or_none(row.get("rolling_bias")),
        rolling_wape=_float_or_none(row.get("rolling_wape")),
        profile_count=int(row.get("profile_count") or 0),
        created_at=row.get("created_at"),
    )


def _load_latest_snapshot_summary(
    session,
    config: PredictionMediumConfig,
) -> PredictionSnapshotSummary | None:
    if not _table_exists(session, SNAPSHOT_TABLE):
        return None

    row = (
        session.execute(
            text(
                """
                /* prediction_performance:snapshot_summary */
                SELECT
                    medium_key,
                    selection_mode,
                    forecast_period_start,
                    forecast_period_end,
                    forecast_period_label,
                    forecast_cadence,
                    selection_run_id,
                    COUNT(*)::integer AS snapshot_count,
                    COUNT(*) FILTER (WHERE uses_fallback)::integer AS fallback_count,
                    COUNT(*) FILTER (
                        WHERE selected_model_version <> global_model_version
                           OR selected_model_key <> global_model_key
                    )::integer AS selected_differs_from_global_count,
                    MAX(created_at) AS latest_created_at
                FROM monitoring.prediction_selected_model_snapshots
                WHERE medium_key = :medium_key
                GROUP BY
                    medium_key,
                    selection_mode,
                    forecast_period_start,
                    forecast_period_end,
                    forecast_period_label,
                    forecast_cadence,
                    selection_run_id
                ORDER BY
                    CASE selection_mode WHEN 'active' THEN 0 ELSE 1 END,
                    forecast_period_start DESC,
                    latest_created_at DESC
                LIMIT 1
                """
            ),
            {"medium_key": config.medium_key},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None

    identity = _snapshot_identity_params(row)
    return PredictionSnapshotSummary(
        medium_key=config.medium_key,
        selection_mode=str(row["selection_mode"]),
        selection_run_id=_int_or_none(row.get("selection_run_id")),
        forecast_period_start=row["forecast_period_start"],
        forecast_period_end=row["forecast_period_end"],
        forecast_period_label=row.get("forecast_period_label"),
        forecast_cadence=str(row["forecast_cadence"]),
        snapshot_count=int(row.get("snapshot_count") or 0),
        fallback_count=int(row.get("fallback_count") or 0),
        selected_differs_from_global_count=int(
            row.get("selected_differs_from_global_count") or 0
        ),
        latest_created_at=row.get("latest_created_at"),
        model_distribution=_load_model_distribution(session, identity),
        fallback_distribution=_load_fallback_distribution(session, identity),
    )


def _load_model_distribution(
    session,
    identity: Mapping[str, object],
) -> list[PredictionDistributionRecord]:
    rows = (
        session.execute(
            text(
                """
                /* prediction_performance:model_distribution */
                SELECT
                    selected_model_version,
                    selected_model_name,
                    COUNT(*)::integer AS row_count
                FROM monitoring.prediction_selected_model_snapshots
                WHERE medium_key = :medium_key
                  AND selection_mode = :selection_mode
                  AND forecast_period_start = :forecast_period_start
                  AND forecast_period_end = :forecast_period_end
                  AND forecast_cadence = :forecast_cadence
                GROUP BY selected_model_version, selected_model_name
                ORDER BY row_count DESC, selected_model_version
                """
            ),
            identity,
        )
        .mappings()
        .all()
    )
    return [
        PredictionDistributionRecord(
            key=str(row["selected_model_version"]),
            label=str(row["selected_model_name"]),
            count=int(row.get("row_count") or 0),
        )
        for row in rows
    ]


def _load_fallback_distribution(
    session,
    identity: Mapping[str, object],
) -> list[PredictionDistributionRecord]:
    rows = (
        session.execute(
            text(
                """
                /* prediction_performance:fallback_distribution */
                SELECT
                    fallback_reason,
                    COUNT(*)::integer AS row_count
                FROM monitoring.prediction_selected_model_snapshots
                WHERE medium_key = :medium_key
                  AND selection_mode = :selection_mode
                  AND forecast_period_start = :forecast_period_start
                  AND forecast_period_end = :forecast_period_end
                  AND forecast_cadence = :forecast_cadence
                GROUP BY fallback_reason
                ORDER BY row_count DESC, fallback_reason
                """
            ),
            identity,
        )
        .mappings()
        .all()
    )
    return [
        PredictionDistributionRecord(
            key=str(row["fallback_reason"]),
            label=str(row["fallback_reason"]),
            count=int(row.get("row_count") or 0),
        )
        for row in rows
    ]


def _load_worst_identifier_selections(
    session,
    config: PredictionMediumConfig,
) -> list[PredictionIdentifierSelectionRecord]:
    if not _table_exists(session, SNAPSHOT_TABLE):
        return []
    latest = _load_latest_snapshot_identity(session, config)
    if latest is None:
        return []

    rows = (
        session.execute(
            text(
                """
                /* prediction_performance:worst_identifiers */
                SELECT
                    medium_key,
                    identifier,
                    selection_mode,
                    selection_run_id,
                    forecast_period_start,
                    forecast_period_end,
                    forecast_period_label,
                    selected_model_version,
                    selected_model_name,
                    global_model_version,
                    global_model_name,
                    uses_fallback,
                    fallback_reason,
                    validation_total_count,
                    matched_validation_count,
                    coverage,
                    mae,
                    rmse,
                    bias,
                    wape,
                    created_at
                FROM monitoring.prediction_selected_model_snapshots
                WHERE medium_key = :medium_key
                  AND selection_mode = :selection_mode
                  AND forecast_period_start = :forecast_period_start
                  AND forecast_period_end = :forecast_period_end
                  AND forecast_cadence = :forecast_cadence
                ORDER BY
                    uses_fallback DESC,
                    wape DESC NULLS LAST,
                    mae DESC NULLS LAST,
                    coverage ASC NULLS LAST,
                    identifier ASC
                LIMIT :limit
                """
            ),
            {**latest, "limit": WORST_IDENTIFIER_LIMIT},
        )
        .mappings()
        .all()
    )
    return [
        PredictionIdentifierSelectionRecord(
            medium_key=config.medium_key,
            medium_label=config.medium_label,
            identifier=str(row["identifier"]),
            selection_mode=str(row["selection_mode"]),
            selection_run_id=_int_or_none(row.get("selection_run_id")),
            forecast_period_start=row["forecast_period_start"],
            forecast_period_end=row["forecast_period_end"],
            forecast_period_label=row.get("forecast_period_label"),
            selected_model_version=int(row["selected_model_version"]),
            selected_model_name=str(row["selected_model_name"]),
            global_model_version=int(row["global_model_version"]),
            global_model_name=str(row["global_model_name"]),
            uses_fallback=bool(row.get("uses_fallback")),
            fallback_reason=str(row.get("fallback_reason") or ""),
            validation_total_count=_int_or_none(row.get("validation_total_count")),
            matched_validation_count=_int_or_none(row.get("matched_validation_count")),
            coverage=_float_or_none(row.get("coverage")),
            mae=_float_or_none(row.get("mae")),
            rmse=_float_or_none(row.get("rmse")),
            bias=_float_or_none(row.get("bias")),
            wape=_float_or_none(row.get("wape")),
            created_at=row.get("created_at"),
        )
        for row in rows
    ]


def _load_latest_snapshot_identity(
    session,
    config: PredictionMediumConfig,
) -> dict[str, object] | None:
    row = (
        session.execute(
            text(
                """
                /* prediction_performance:snapshot_identity */
                SELECT
                    medium_key,
                    selection_mode,
                    forecast_period_start,
                    forecast_period_end,
                    forecast_cadence,
                    MAX(created_at) AS latest_created_at
                FROM monitoring.prediction_selected_model_snapshots
                WHERE medium_key = :medium_key
                GROUP BY
                    medium_key,
                    selection_mode,
                    forecast_period_start,
                    forecast_period_end,
                    forecast_cadence
                ORDER BY
                    CASE selection_mode WHEN 'active' THEN 0 ELSE 1 END,
                    forecast_period_start DESC,
                    latest_created_at DESC
                LIMIT 1
                """
            ),
            {"medium_key": config.medium_key},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return _snapshot_identity_params(row)


def _snapshot_identity_params(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "medium_key": row["medium_key"],
        "selection_mode": row["selection_mode"],
        "forecast_period_start": row["forecast_period_start"],
        "forecast_period_end": row["forecast_period_end"],
        "forecast_cadence": row["forecast_cadence"],
    }


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
