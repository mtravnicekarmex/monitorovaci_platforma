from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Text, Float, Boolean, BigInteger, Integer, Numeric, DateTime, func, Index, \
    UniqueConstraint, text, CheckConstraint
from geoalchemy2 import Geometry
from typing import List



class Base(DeclarativeBase):
    pass



# areálové kalorimetry monitoring na MS
class Kalorimetr_areal_Zarizeni(Base):
    __tablename__ = 'Zarizeni_kalorimetry'
    __table_args__ = {'schema': 'dbo'}

    identifikace: Mapped[str] = mapped_column(String(250), primary_key=True, nullable=False, unique=True)
    seriove_cislo: Mapped[int] = mapped_column(BigInteger, nullable=True)
    MBUS: Mapped[int] = mapped_column(BigInteger, nullable=True)
    objekt: Mapped[str] = mapped_column(String(250), nullable=True)
    patro: Mapped[str] = mapped_column(String(10), nullable=True)
    mistnost: Mapped[str] = mapped_column(String(250), nullable=True)
    umisteni: Mapped[str] = mapped_column(String(250), nullable=True)
    napaji: Mapped[str] = mapped_column(String(250), nullable=True)
    zdroj: Mapped[str] = mapped_column(String(250), nullable=True)
    zdroj_mereni: Mapped[str] = mapped_column(String(250), nullable=True)
    koncovy_odberatel: Mapped[str] = mapped_column(String(250), nullable=True)
    platnost_cejchu: Mapped[datetime] = mapped_column(nullable=True)
    poznamka_kalorimetry: Mapped[str] = mapped_column(String(250), nullable=True)
    foto: Mapped[str] = mapped_column(String(550), nullable=True)


    # Relationships

    mereni: Mapped[List["Kalorimetr_areal_Mereni"]] = relationship("Kalorimetr_areal_Mereni", back_populates="zarizeni")

    def __repr__(self) -> str:
        return f"{self.identifikace} - {self.seriove_cislo}"



# areálové kalorimetry měření monitoring na MS
class Kalorimetr_areal_Mereni(Base):
    __tablename__ = 'Mereni_Kalorimetr'
    __table_args__ = {'schema': 'dbo'}

    recid: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, nullable=False, unique=True)
    identifikace: Mapped[str] = mapped_column(String(250), ForeignKey('dbo.Zarizeni_kalorimetry.identifikace'), nullable=True)
    seriove_cislo: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    spotreba_energie: Mapped[float] = mapped_column(nullable=False, unique=True)
    objem: Mapped[float] = mapped_column(nullable=True)
    platne: Mapped[bool] = mapped_column(nullable=True)
    date: Mapped[datetime] = mapped_column("datum", nullable=True)

    # Relationships

    zarizeni: Mapped["Kalorimetr_areal_Zarizeni"] = relationship("Kalorimetr_areal_Zarizeni", back_populates="mereni")

    def __repr__(self) -> str:
        return f"{self.date} - {self.odberne_misto} - {self.hodnota}"




# areálové kalorimetry QGIS na PG
class Kalorimetr_areal_Zarizeni_QGIS(Base):
    __tablename__ = 'kalorimetry'
    __table_args__ = {'schema': 'evidence'}

    identifikace: Mapped[str] = mapped_column(String(250), primary_key=True, nullable=False, unique=True)
    geom: Mapped[Geometry] = mapped_column(Geometry(geometry_type='POINT', srid=5514, spatial_index=True), nullable=True)
    seriove_cislo: Mapped[int] = mapped_column(BigInteger, nullable=True)
    MBUS: Mapped[int] = mapped_column(BigInteger, nullable=True)
    objekt: Mapped[str] = mapped_column(String(250), nullable=True)
    patro: Mapped[str] = mapped_column(String(10), nullable=True)
    mistnost: Mapped[str] = mapped_column(String(250), nullable=True)
    umisteni: Mapped[str] = mapped_column(String(250), nullable=True)
    napaji: Mapped[str] = mapped_column(String(250), nullable=True)
    zdroj: Mapped[str] = mapped_column(String(250), nullable=True)
    zdroj_mereni: Mapped[str] = mapped_column(String(250), nullable=True)
    koncovy_odberatel: Mapped[str] = mapped_column(String(250), nullable=True)
    platnost_cejchu: Mapped[datetime] = mapped_column(nullable=True)
    poznamka_kalorimetry: Mapped[str] = mapped_column(String(250), nullable=True)
    foto: Mapped[str] = mapped_column(String(550), nullable=True)


    def __repr__(self) -> str:
        return f"{self.identifikace} - {self.seriove_cislo}"


# arealove kalorimetry monitoring na PG
class Mereni_kalorimetry(Base):
    __tablename__ = "Mereni_kalorimetry_vse"
    __table_args__ = (
        UniqueConstraint("identifikace", "date", "zdroj", name="uq_kalorimetry_ident_date_zdroj"),
        UniqueConstraint("source_recid", "zdroj", name="uq_kalorimetry_source_recid_zdroj"),
        Index("ix_kalorimetry_ident_interval_slot", "identifikace", "interval_minutes", "day_of_week", "slot"),
        Index("ix_kalorimetry_ident_date_desc", "identifikace", "date"),
        Index("ix_kalorimetry_date_desc", "date"),
        Index("ix_kalorimetry_vse_time_utc", "time_utc"),
        Index("ix_kalorimetry_vse_ident_time_utc", "identifikace", "time_utc"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_recid: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    seriove_cislo: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    source_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_basis: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_utc_offset_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_fold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp_position: Mapped[str | None] = mapped_column(String(20), nullable=True)
    spotreba_energie: Mapped[float] = mapped_column(Float, nullable=False)
    objem: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    nocni_odber: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    platne: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    gap_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    zdroj: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    reset_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class KalorimetryProfilesAnomaly(Base):
    __tablename__ = "kalorimetry_anomaly_profiles"
    __table_args__ = (
        UniqueConstraint(
            "identifikace",
            "interval_minutes",
            "day_of_week",
            "slot",
            "model_version",
            name="uq_kalorimetry_profile_key",
        ),
        Index(
            "ix_kalorimetry_profile_lookup",
            "identifikace",
            "interval_minutes",
            "day_of_week",
            "slot",
        ),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    median: Mapped[float] = mapped_column(Float, nullable=False)
    mean: Mapped[float] = mapped_column(Float, nullable=False)
    p10: Mapped[float] = mapped_column(Float, nullable=False)
    p90: Mapped[float] = mapped_column(Float, nullable=False)
    std: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        nullable=False,
    )


class KalorimetryWeatherModelProfile(Base):
    __tablename__ = "kalorimetry_weather_model_profiles"
    __table_args__ = (
        UniqueConstraint(
            "identifikace",
            "interval_minutes",
            "day_of_week",
            "slot",
            "model_version",
            name="uq_kalorimetry_weather_profile_key",
        ),
        Index(
            "ix_kalorimetry_weather_profile_lookup",
            "identifikace",
            "interval_minutes",
            "day_of_week",
            "slot",
        ),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    base_mean: Mapped[float] = mapped_column(Float, nullable=False)
    hdd_slope: Mapped[float] = mapped_column(Float, nullable=False)
    hdd_24h_mean: Mapped[float] = mapped_column(Float, nullable=False)
    residual_mean: Mapped[float] = mapped_column(Float, nullable=False)
    residual_median: Mapped[float] = mapped_column(Float, nullable=False)
    residual_p10: Mapped[float] = mapped_column(Float, nullable=False)
    residual_p90: Mapped[float] = mapped_column(Float, nullable=False)
    residual_std: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        nullable=False,
    )


class KalorimetryModelSelectionRun(Base):
    __tablename__ = "kalorimetry_model_selection_runs"
    __table_args__ = (
        Index("ix_kalorimetry_model_selection_runs_created", "created_at"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    train_start: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    train_end: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    validation_start: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    validation_end: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    deploy_start: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    deploy_end: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    selected_model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        nullable=False,
    )


class KalorimetryModelValidationRun(Base):
    __tablename__ = "kalorimetry_model_validation_runs"
    __table_args__ = (
        Index(
            "ix_kalorimetry_model_validation_runs_model_reference",
            "model_version",
            "reference_end",
        ),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_key: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
    )
    fold_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        nullable=False,
    )


class KalorimetryModelValidationMetric(Base):
    __tablename__ = "kalorimetry_model_validation_metrics"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "identifikace",
            name="uq_kalorimetry_validation_metric_run_ident",
        ),
        Index("ix_kalorimetry_validation_metric_run", "run_id"),
        Index(
            "ix_kalorimetry_validation_metric_model_wape",
            "model_version",
            "wape",
        ),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey(
            "monitoring.kalorimetry_model_validation_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    rolling_backtest_fold_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    matched_fold_count: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_validation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    coverage: Mapped[float] = mapped_column(Float, nullable=False)
    mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    rmse: Mapped[float | None] = mapped_column(Float, nullable=True)
    bias: Mapped[float | None] = mapped_column(Float, nullable=True)
    wape: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        nullable=False,
    )


class KalorimetryAnomalyScore(Base):
    __tablename__ = "kalorimetry_anomaly_scores"
    __table_args__ = (
        UniqueConstraint(
            "measurement_id",
            "model_version",
            name="uq_kalorimetry_score_measurement_model",
        ),
        Index(
            "ix_kalorimetry_score_ident_date",
            "identifikace",
            "date",
        ),
        Index("ix_kalorimetry_score_is_anomaly", "is_anomaly"),
        Index("ix_kalorimetry_score_processed", "processed"),
        Index(
            "ix_kalorimetry_score_selection_snapshot",
            "selection_snapshot_id",
        ),
        Index(
            "ix_kalorimetry_score_profile_snapshot",
            "profile_snapshot_id",
        ),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    measurement_id: Mapped[int] = mapped_column(
        ForeignKey(
            "monitoring.Mereni_kalorimetry_vse.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    actual_value: Mapped[float] = mapped_column(Float, nullable=False)
    expected_mean: Mapped[float] = mapped_column(Float, nullable=False)
    expected_std: Mapped[float] = mapped_column(Float, nullable=False)
    expected_median: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_p10: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_p90: Mapped[float | None] = mapped_column(Float, nullable=True)
    deviation: Mapped[float] = mapped_column(Float, nullable=False)
    z_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, nullable=False)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    selection_snapshot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_snapshot_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        nullable=False,
    )
    processed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )


class KalorimetryScoringState(Base):
    __tablename__ = "kalorimetry_scoring_state"
    __table_args__ = {"schema": "monitoring"}

    model_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_measurement_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )


class KalorimetryAnomalyEvent(Base):
    __tablename__ = "kalorimetry_anomaly_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('SPIKE','SUSTAINED_HIGH_USAGE')",
            name="ck_kalorimetry_event_type_valid",
        ),
        Index(
            "uq_kalorimetry_event_active",
            "identifikace",
            "event_type",
            "model_version",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
        Index(
            "ix_kalorimetry_event_lookup",
            "identifikace",
            "event_type",
            "model_version",
        ),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_z_score: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    last_score_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        nullable=False,
    )


class KalorimetryEventState(Base):
    __tablename__ = "kalorimetry_event_state"
    __table_args__ = (
        UniqueConstraint(
            "identifikace",
            "event_type",
            "model_version",
            name="uq_kalorimetry_event_state_identity",
        ),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    consecutive_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_event_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    event_start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    max_z_score: Mapped[float] = mapped_column(Float, nullable=False)
    last_score_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )


class KalorimetryEventEngineState(Base):
    __tablename__ = "kalorimetry_event_engine_state"
    __table_args__ = {"schema": "monitoring"}

    model_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_score_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )


class KalorimetryOutlierReview(Base):
    __tablename__ = "kalorimetry_outlier_reviews"
    __table_args__ = (
        CheckConstraint(
            "detection_kind IN ('NORMAL_DELTA','GAP_MEAN')",
            name="ck_kalorimetry_outlier_review_detection_kind_valid",
        ),
        CheckConstraint(
            "review_status IN ('PENDING','CONFIRMED_OUTLIER','CONFIRMED_CONSUMPTION')",
            name="ck_kalorimetry_outlier_review_status_valid",
        ),
        UniqueConstraint("identifikace", "date", "zdroj", name="uq_kalorimetry_outlier_review_ident_date_source"),
        Index("ix_kalorimetry_outlier_review_status_date", "review_status", "date"),
        Index("ix_kalorimetry_outlier_review_ident_date", "identifikace", "date"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    zdroj: Mapped[str] = mapped_column(String(20), nullable=False)
    source_recid: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    seriove_cislo: Mapped[str] = mapped_column(String(100), nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    detection_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    current_objem: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_objem: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    candidate_delta: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    median_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    p90_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    p99_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    std_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'PENDING'"))
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(250), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=text("now()"), nullable=False)
