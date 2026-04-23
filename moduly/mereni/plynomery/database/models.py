from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Text, Float, Boolean, BigInteger, Integer, Numeric, DateTime, func, Index, \
    UniqueConstraint, text, CheckConstraint
from geoalchemy2 import Geometry
from typing import List



class Base(DeclarativeBase):
    pass




# areálové plynoměry monitoring na MS
class Plynomer_areal_Zarizeni(Base):
    __tablename__ = 'Zarizeni_plynomery'
    __table_args__ = {'schema': 'dbo'}

    identifikace: Mapped[str] = mapped_column(String(250), primary_key=True, nullable=False, unique=True)
    seriove_cislo: Mapped[str] = mapped_column(String(250), nullable=True)
    MBUS: Mapped[str] = mapped_column(String(250), nullable=True)
    pozice: Mapped[str] = mapped_column(String(250), nullable=True)
    podruzny: Mapped[str] = mapped_column(String(250), nullable=True)
    mistnost: Mapped[str] = mapped_column(String(250), nullable=True)
    objekt: Mapped[str] = mapped_column(String(50), nullable=True)
    patro: Mapped[str] = mapped_column(String(10), nullable=True)
    umisteni: Mapped[str] = mapped_column(String(250), nullable=True)
    napaji: Mapped[str] = mapped_column(String(250), nullable=True)
    koncovy_odberatel: Mapped[str] = mapped_column(String(250), nullable=True)
    platnost_cejchu: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    poznamka_plynomery: Mapped[str] = mapped_column(String(250), nullable=True)
    foto: Mapped[str] = mapped_column(String(550), nullable=True)


    # Relationships

    mereni: Mapped[List["Plynomer_areal_Mereni"]] = relationship("Plynomer_areal_Mereni", back_populates="zarizeni")

    def __repr__(self) -> str:
        return f"{self.identifikace} - {self.seriove_cislo} - {self.MBUS} - {self.platnost_cejchu}"





# areálové plynoměry měření monitoring na MS
class Plynomer_areal_Mereni(Base):
    __tablename__ = 'Mereni_plynomery'
    __table_args__ = {'schema': 'dbo'}


    recid: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    identifikace: Mapped[str] = mapped_column(String(250), ForeignKey('dbo.Zarizeni_plynomery.identifikace'), nullable=False)
    seriove_cislo: Mapped[int] = mapped_column(BigInteger, nullable=True)
    objem: Mapped[float] = mapped_column(Float, nullable=True)
    platne: Mapped[bool] = mapped_column(Boolean, nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)

    # Relationships

    zarizeni: Mapped["Plynomer_areal_Zarizeni"] = relationship("Plynomer_areal_Zarizeni", back_populates="mereni")

    def __repr__(self) -> str:
        return f"{self.date} - {self.identifikace} - {self.objem}"



# areálové plynoměry QGIS dbo na PG
class Plynomer_areal_Zarizeni_QGIS(Base):
    __tablename__ = 'plynoměry'
    __table_args__ = {'schema': 'evidence'}

    identifikace: Mapped[str] = mapped_column(String(250), primary_key=True, nullable=False, unique=True)
    geom: Mapped[Geometry] = mapped_column(Geometry(geometry_type='POINT', srid=5514, spatial_index=True), nullable=True)
    seriove_cislo: Mapped[str] = mapped_column(String(250), nullable=True)
    MBUS: Mapped[str] = mapped_column(String(250), nullable=True)
    pozice: Mapped[str] = mapped_column(String(250), nullable=True)
    podruzny: Mapped[str] = mapped_column(String(250), nullable=True)
    mistnost: Mapped[str] = mapped_column(String(250), nullable=True)
    patro: Mapped[str] = mapped_column(String(10), nullable=True)
    objekt: Mapped[str] = mapped_column(String(50), nullable=True)
    umisteni: Mapped[str] = mapped_column(String(250), nullable=True)
    napaji: Mapped[str] = mapped_column(String(250), nullable=True)
    koncovy_odberatel: Mapped[str] = mapped_column(String(250), nullable=True)
    platnost_cejchu: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    poznamka_plynomery: Mapped[str] = mapped_column(String(250), nullable=True)
    foto: Mapped[str] = mapped_column(String(550), nullable=True)

    def __repr__(self) -> str:
        return f"{self.identifikace} - {self.seriove_cislo} - {self.MBUS} - {self.platnost_cejchu}"


# areálové plynoměry monitoring na PG, připraveno pro anomaly pipeline
class Mereni_plynomery(Base):
    __tablename__ = "Mereni_plynomery_vse"
    __table_args__ = (
        UniqueConstraint("identifikace", "date", "zdroj", name="uq_plynomery_ident_date_zdroj"),
        UniqueConstraint("source_recid", "zdroj", name="uq_plynomery_source_recid_zdroj"),
        Index("ix_plynomery_ident_interval_slot", "identifikace", "interval_minutes", "day_of_week", "slot"),
        Index("ix_plynomery_ident_date_desc", "identifikace", "date"),
        Index("ix_plynomery_date_desc", "date"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_recid: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    seriove_cislo: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    objem: Mapped[float] = mapped_column(Float, nullable=False)
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


class PlynomeryProfilesAnomaly(Base):
    __tablename__ = "plynomery_anomaly_profiles"
    __table_args__ = (
        UniqueConstraint(
            "identifikace",
            "interval_minutes",
            "day_of_week",
            "slot",
            "model_version",
            name="uq_plynomery_profile_key",
        ),
        Index(
            "ix_plynomery_profile_lookup",
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        nullable=False,
    )
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)


class PlynomeryAnomalyScore(Base):
    __tablename__ = "plynomery_anomaly_scores"
    __table_args__ = (
        UniqueConstraint("measurement_id", "model_version", name="uq_plynomery_score_measurement_model"),
        Index("ix_plynomery_score_ident_date", "identifikace", "date"),
        Index("ix_plynomery_score_is_anomaly", "is_anomaly"),
        Index("ix_plynomery_score_processed", "processed"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    measurement_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring.Mereni_plynomery_vse.id", ondelete="CASCADE"),
        nullable=False,
    )
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    actual_value: Mapped[float] = mapped_column(Float, nullable=False)
    expected_mean: Mapped[float] = mapped_column(Float, nullable=False)
    expected_std: Mapped[float] = mapped_column(Float, nullable=False)
    expected_median: Mapped[float] = mapped_column(Float, nullable=False)
    expected_p10: Mapped[float] = mapped_column(Float, nullable=False)
    expected_p90: Mapped[float] = mapped_column(Float, nullable=False)
    deviation: Mapped[float] = mapped_column(Float, nullable=False)
    z_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, nullable=False)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=text("now()"), nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class PlynomeryScoringState(Base):
    __tablename__ = "plynomery_scoring_state"
    __table_args__ = {"schema": "monitoring"}

    model_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_measurement_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )


class PlynomeryExpectedZero(Base):
    __tablename__ = "plynomery_expected_zero"
    __table_args__ = {"schema": "monitoring"}

    identifikace: Mapped[str] = mapped_column(String(250), primary_key=True)
    updated_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )


class PlynomeryOutlierReview(Base):
    __tablename__ = "plynomery_outlier_reviews"
    __table_args__ = (
        CheckConstraint(
            "detection_kind IN ('NORMAL_DELTA','GAP_MEAN')",
            name="ck_plynomery_outlier_review_detection_kind_valid",
        ),
        CheckConstraint(
            "review_status IN ('PENDING','CONFIRMED_OUTLIER','CONFIRMED_CONSUMPTION')",
            name="ck_plynomery_outlier_review_status_valid",
        ),
        UniqueConstraint("identifikace", "date", "zdroj", name="uq_plynomery_outlier_review_ident_date_source"),
        Index("ix_plynomery_outlier_review_status_date", "review_status", "date"),
        Index("ix_plynomery_outlier_review_ident_date", "identifikace", "date"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    zdroj: Mapped[str] = mapped_column(String(20), nullable=False)
    source_recid: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    seriove_cislo: Mapped[str] = mapped_column(String(250), nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    detection_kind: Mapped[str] = mapped_column(String(20), nullable=False)
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
    review_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'PENDING'"),
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        nullable=False,
    )


class PlynomeryOutlierEmailDelivery(Base):
    __tablename__ = "plynomery_outlier_email_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','SENT','FAILED','SKIPPED')",
            name="ck_plynomery_outlier_email_delivery_status_valid",
        ),
        UniqueConstraint(
            "review_id",
            "rule_id",
            "recipient_email",
            name="uq_plynomery_outlier_email_delivery_review_rule_recipient",
        ),
        Index("ix_plynomery_outlier_email_delivery_status", "status"),
        Index("ix_plynomery_outlier_email_delivery_recipient_created", "recipient_email", "created_at"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring.plynomery_outlier_reviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("monitoring.plynomery_alert_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    review_date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    zdroj: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    detection_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(250), nullable=False)
    summary_group_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'PENDING'"))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=text("now()"), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class PlynomeryAnomalyEvent(Base):
    __tablename__ = "plynomery_anomaly_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('NIGHT_USAGE','SPIKE','LONG_HIGH_USAGE','EXPECTED_ZERO_USAGE')",
            name="ck_plynomery_event_type_valid",
        ),
        Index(
            "uq_plynomery_event_active_true",
            "identifikace",
            "event_type",
            "model_version",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
        Index("ix_plynomery_event_lookup", "identifikace", "event_type", "model_version"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_z_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_z_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_deviation: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_score_time: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=text("now()"), nullable=False)


class PlynomeryEventState(Base):
    __tablename__ = "plynomery_event_state"
    __table_args__ = (
        UniqueConstraint("identifikace", "event_type", "model_version", name="uq_plynomery_event_state_unique"),
        Index("ix_plynomery_event_state_lookup", "identifikace", "event_type", "model_version"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    consecutive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accumulator: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_event_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    event_start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_score_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class PlynomeryEventEngineState(Base):
    __tablename__ = "plynomery_event_engine_state"
    __table_args__ = {"schema": "monitoring"}

    id: Mapped[int] = mapped_column(primary_key=True)
    model_version: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    last_score_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=text("now()"), nullable=False)


class PlynomeryAlertRule(Base):
    __tablename__ = "plynomery_alert_rules"
    __table_args__ = (
        CheckConstraint(
            "event_type IS NULL OR event_type IN ('NIGHT_USAGE','SPIKE','LONG_HIGH_USAGE','EXPECTED_ZERO_USAGE','OUTLIER_REVIEW')",
            name="ck_plynomery_alert_rule_event_type_valid",
        ),
        CheckConstraint(
            "severity_min IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_plynomery_alert_rule_severity_min_valid",
        ),
        CheckConstraint(
            "send_on IN ('ACTIVE','RESOLVED','BOTH')",
            name="ck_plynomery_alert_rule_send_on_valid",
        ),
        CheckConstraint(
            "min_duration_minutes >= 0",
            name="ck_plynomery_alert_rule_min_duration_non_negative",
        ),
        Index("ix_plynomery_alert_rule_enabled", "enabled"),
        Index("ix_plynomery_alert_rule_ident_event", "identifikace", "event_type", "enabled"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_name: Mapped[str] = mapped_column(String(150), nullable=False)
    identifikace: Mapped[str | None] = mapped_column(String(250), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    severity_min: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'HIGH'"))
    min_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("120"))
    send_on: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'ACTIVE'"))
    recipient_email: Mapped[str] = mapped_column(String(250), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=text("now()"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )


class PlynomeryAlertDelivery(Base):
    __tablename__ = "plynomery_alert_deliveries"
    __table_args__ = (
        CheckConstraint(
            "alert_state IN ('ACTIVE_THRESHOLD','RESOLVED')",
            name="ck_plynomery_alert_delivery_state_valid",
        ),
        CheckConstraint(
            "status IN ('PENDING','SENT','FAILED','SKIPPED')",
            name="ck_plynomery_alert_delivery_status_valid",
        ),
        UniqueConstraint(
            "event_id",
            "rule_id",
            "alert_state",
            "recipient_email",
            name="uq_plynomery_alert_delivery_event_rule_state_recipient",
        ),
        Index("ix_plynomery_alert_delivery_status", "status"),
        Index("ix_plynomery_alert_delivery_recipient_created", "recipient_email", "created_at"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring.plynomery_anomaly_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("monitoring.plynomery_alert_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(250), nullable=False)
    alert_state: Mapped[str] = mapped_column(String(20), nullable=False)
    summary_group_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'PENDING'"))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=text("now()"), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


