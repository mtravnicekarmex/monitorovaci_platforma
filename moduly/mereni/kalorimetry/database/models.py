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
