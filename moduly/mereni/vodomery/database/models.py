from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Text, Float, Boolean, BigInteger, Integer, Numeric, DateTime, func, Index, \
    UniqueConstraint, text, CheckConstraint
from geoalchemy2 import Geometry
from typing import List



class Base(DeclarativeBase):
    pass



# SČVK vodoměry dbo na PG
class Vodomer_SCVK_Zarizeni(Base):
    __tablename__ = 'Zarizeni_vodomery_SCVK'
    __table_args__ = {'schema': 'dbo'}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    odberne_misto: Mapped[str] = mapped_column(nullable=False)
    seriove_cislo: Mapped[str] = mapped_column(nullable=False, unique=True)
    MBUS: Mapped[str] = mapped_column(String(20), nullable=False)
    mm_id: Mapped[str] = mapped_column(String(20), nullable=True)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=True)
    instalovano: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    # Relationships
    alarmy: Mapped[List["Vodomer_SCVK_Alarm"]] = relationship("Vodomer_SCVK_Alarm", back_populates="zarizeni")
    mereni: Mapped[List["Vodomer_SCVK_Mereni"]] = relationship("Vodomer_SCVK_Mereni", back_populates="zarizeni")


    def __repr__(self) -> str:
        return f"{self.identifikace} - {self.seriove_cislo} - {self.identifikace} - {self.instalovano}"



# SČVK alarm pro vodoměry dbo na PG
class Vodomer_SCVK_Alarm(Base):
    __tablename__ = 'Alarmy_vodomery_SCVK'
    __table_args__ = {'schema': 'dbo'}

    recid: Mapped[str] = mapped_column(String(36), primary_key=True) # UUID
    odberne_misto: Mapped[str] = mapped_column(nullable=False)
    seriove_cislo : Mapped[str] = mapped_column(ForeignKey('dbo.Zarizeni_vodomery_SCVK.seriove_cislo'), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    alarm_start: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    alarm_stop: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=True)

    # Relationship
    zarizeni: Mapped["Vodomer_SCVK_Zarizeni"] = relationship("Vodomer_SCVK_Zarizeni", back_populates="alarmy")


    def __repr__(self) -> str:
        return f"{self.odberne_misto} - {self.seriove_cislo} - {self.alarm_start} - {self.type}"



# SČVK měření vodoměry dbo na PG
class Vodomer_SCVK_Mereni(Base):
    __tablename__ = 'Mereni_vodomery_SCVK'
    __table_args__ = {'schema': 'dbo'}

    recid: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    odberne_misto: Mapped[str] = mapped_column(nullable=False)
    seriove_cislo: Mapped[str] = mapped_column(ForeignKey('dbo.Zarizeni_vodomery_SCVK.seriove_cislo'), nullable=False)
    objem: Mapped[float] = mapped_column(Float, nullable=False)
    platne: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    temp: Mapped[float] = mapped_column(Float, nullable=True)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=True)

    # Relationship
    zarizeni: Mapped["Vodomer_SCVK_Zarizeni"] = relationship("Vodomer_SCVK_Zarizeni", back_populates="mereni")


    def __repr__(self) -> str:
        return f"{self.odberne_misto} - {self.seriove_cislo} - {self.objem}"





# areálové + SČVK vodoměry zařízení monitoring na MS
class Vodomer_areal_Zarizeni(Base):
    __tablename__ = 'Zarizeni_vodomery'
    __table_args__ = {'schema': 'dbo'}


    identifikace: Mapped[str] = mapped_column(String(250), primary_key=True, nullable=False, unique=True)
    seriove_cislo: Mapped[str] = mapped_column(String(250), unique=True, nullable=True)
    MBUS: Mapped[str] = mapped_column(String(250), nullable=False)
    pozice: Mapped[str] = mapped_column(String(250), nullable=True)
    podruzny: Mapped[str] = mapped_column(String(250), nullable=True)
    mistnost: Mapped[str] = mapped_column(String(250), nullable=True)
    objekt: Mapped[str] = mapped_column(String(50), nullable=True)
    patro: Mapped[str] = mapped_column(String(10), nullable=True)
    umisteni: Mapped[str] = mapped_column(String(250), nullable=True)
    napaji: Mapped[str] = mapped_column(String(250), nullable=True)
    koncovy_odberatel: Mapped[str] = mapped_column(String(250), nullable=True)
    platnost_cejchu: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    redukcni_ventil: Mapped[str] = mapped_column(String(250), nullable=True)
    filtr: Mapped[str] = mapped_column(String(250), nullable=True)
    poznamka_vodomery: Mapped[str] = mapped_column(String(250), nullable=True)
    foto: Mapped[str] = mapped_column(String(550), nullable=True)


    # Relationships

    mereni: Mapped[List["Vodomer_areal_Mereni"]] = relationship("Vodomer_areal_Mereni", back_populates="zarizeni")
    mereni_vse: Mapped[List["Mereni_vodomery"]] = relationship("Mereni_vodomery", primaryjoin="Vodomer_areal_Zarizeni.identifikace==foreign(Mereni_vodomery.identifikace)", viewonly=True,)
    # mereni_SCVK: Mapped[List["Vodomer_SCVK_Mereni_MS"]] = relationship("Vodomer_SCVK_Mereni_MS", back_populates="zarizeni")

    def __repr__(self) -> str:
        return f"{self.identifikace} - {self.seriove_cislo} - {self.MBUS} - {self.platnost_cejchu}"




#   areálové vodoměry měření monitoring na MS
class Vodomer_areal_Mereni(Base):
    __tablename__ = 'Mereni_vodomery'
    __table_args__ = {'schema': 'dbo'}


    recid: Mapped[int] = mapped_column(primary_key=True)
    identifikace: Mapped[str] = mapped_column(String(250), ForeignKey('dbo.Zarizeni_vodomery.identifikace'), nullable=False)
    seriove_cislo: Mapped[str] = mapped_column(String(250), nullable=False)
    objem: Mapped[float] = mapped_column(Float, nullable=False)
    platne: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)


    # Relationship
    zarizeni: Mapped["Vodomer_areal_Zarizeni"] = relationship("Vodomer_areal_Zarizeni", back_populates="mereni")

    def __repr__(self) -> str:
        return f"{self.identifikace} - {self.seriove_cislo} - {self.objem}"





# areálové + SČVK vodoměry qgis na PG
class Vodomer_areal_Zarizeni_QGIS(Base):
    __tablename__ = 'vodoměry'
    __table_args__ = {'schema': 'qgis'}


    identifikace: Mapped[str] = mapped_column(String(250), primary_key=True, nullable=False, unique=True)
    geom: Mapped[Geometry] = mapped_column(Geometry(geometry_type='POINT', srid=5514, spatial_index=True), nullable=True)
    seriove_cislo: Mapped[str] = mapped_column(String(250), nullable=True)
    MBUS: Mapped[str] = mapped_column(String(250), nullable=False)
    pozice: Mapped[str] = mapped_column(String(250), nullable=True)
    podruzny: Mapped[str] = mapped_column(String(250), nullable=True)
    mistnost: Mapped[str] = mapped_column(String(250), nullable=True)
    objekt: Mapped[str] = mapped_column(String(50), nullable=True)
    patro: Mapped[str] = mapped_column(String(10), nullable=True)
    umisteni: Mapped[str] = mapped_column(String(250), nullable=True)
    napaji: Mapped[str] = mapped_column(String(250), nullable=True)
    koncovy_odberatel: Mapped[str] = mapped_column(String(250), nullable=True)
    platnost_cejchu: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    redukcni_ventil: Mapped[str] = mapped_column(String(250), nullable=True)
    filtr: Mapped[str] = mapped_column(String(250), nullable=True)
    poznamka_vodomery: Mapped[str] = mapped_column(String(250), nullable=True)
    vetev: Mapped[str] = mapped_column(String(30), nullable=True)
    foto: Mapped[str] = mapped_column(String(550), nullable=True)

    # Relationships
    mereni: Mapped[List["Mereni_vodomery"]] = relationship("Mereni_vodomery", back_populates="zarizeni", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"{self.identifikace} - {self.seriove_cislo} - {self.MBUS} - {self.platnost_cejchu}"






# areálové + SČVK vodoměry měření monitoring na PG, připraveno na alerting
class Mereni_vodomery(Base):
    __tablename__ = "Mereni_vodomery_vse"
    __table_args__ = (UniqueConstraint("identifikace", "date", "zdroj", name="uq_ident_date_zdroj"),
                        UniqueConstraint("source_recid", "zdroj", name="uq_source_recid_zdroj"),
                        Index("ix_ident_interval_slot","identifikace", "interval_minutes", "day_of_week", "slot"),
                        Index("ix_ident_date_desc", "identifikace", "date"),
                        Index("ix_date_desc", "date"),
        {"schema": "monitoring"},
    )

    # vlastní PK v PG
    id: Mapped[int] = mapped_column(primary_key=True)

    # původní recid z MS (pro inkrementální sync)
    source_recid: Mapped[int] = mapped_column(BigInteger, index=True, nullable=True)

    identifikace: Mapped[str] = mapped_column(String(250), ForeignKey('qgis.vodoměry.identifikace', ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
    seriove_cislo: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    objem: Mapped[float] = mapped_column(Float, nullable=False)
    delta: Mapped[float] = mapped_column(Float, nullable=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    nocni_odber: Mapped[bool] = mapped_column(Boolean, default=False)
    platne: Mapped[bool] = mapped_column(Boolean, default=True)
    gap_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # --- Nové produkční flagy ---
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # --- Nové produkční flagy ---
    zdroj: Mapped[str] = mapped_column(String(20), nullable=False)  # AREAL / SCVK
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False) # audit
    reset_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationship
    zarizeni: Mapped["Vodomer_areal_Zarizeni_QGIS"] = relationship("Vodomer_areal_Zarizeni_QGIS", back_populates="mereni")


    def __repr__(self) -> str:
        return f"{self.identifikace} - {self.seriove_cislo} - {self.objem}"






# areálové + SČVK vodoměry anomaly
class VodomeryProfilesAnomaly(Base):
    __tablename__ = "vodomery_anomaly_profiles"
    __table_args__ = (UniqueConstraint("identifikace", "interval_minutes", "day_of_week", "slot", "model_version", name="uq_profile_key"),
                        Index("ix_profile_lookup", "identifikace", "interval_minutes", "day_of_week", "slot"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identifikace: Mapped[str] = mapped_column(String(250), ForeignKey('qgis.vodoměry.identifikace', ondelete="CASCADE"), nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    median: Mapped[float] = mapped_column(Float, nullable=False)
    mean: Mapped[float] = mapped_column(Float, nullable=False)
    p10: Mapped[float] = mapped_column(Float, nullable=False)
    p90: Mapped[float] = mapped_column(Float, nullable=False)
    std: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=text("now()"), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)




# areálové + SČVK vodoměry anomaly score
class VodomeryAnomalyScore(Base):
    __tablename__ = "vodomery_anomaly_scores"
    __table_args__ = (
        UniqueConstraint("measurement_id", "model_version", name="uq_score_measurement_model"),
        Index("ix_score_ident_date", "identifikace", "date"),
        Index("ix_score_is_anomaly", "is_anomaly"),
        Index("ix_score_processed", "processed"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    measurement_id: Mapped[int] = mapped_column(ForeignKey("monitoring.Mereni_vodomery_vse.id", ondelete="CASCADE"), nullable=False)
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
    severity: Mapped[str] = mapped_column(String(20), nullable=True)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=text("now()"), nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))





# pomocná tabulka pro VodomeryAnomalyScore
class VodomeryScoringState(Base):
    __tablename__ = "vodomery_scoring_state"
    __table_args__ = {"schema": "monitoring"}

    model_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_measurement_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=text("now()"), onupdate=text("now()"), nullable=False)




# areálové + SČVK vodoměry event
class VodomeryAnomalyEvent(Base):
    __tablename__ = "vodomery_anomaly_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('NIGHT_USAGE','SPIKE','LONG_LEAK','ZERO_FLOW')", name="ck_event_type_valid"), # povolené typy eventů
        Index("uq_event_active_true","identifikace", "event_type", "model_version", unique=True, postgresql_where=text("is_active = true")), # 🔥 klíčový partial unique index, dovolí jen 1 aktivní event pro danou kombinaci
        Index("ix_event_lookup","identifikace", "event_type", "model_version"), # běžný index pro rychlé filtrování historie

        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identifikace: Mapped[str] = mapped_column(String(250), ForeignKey("qgis.vodoměry.identifikace", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_z_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_z_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_deviation: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    last_score_time: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=text("now()"), nullable=False)





# pomocná tabulka pro VodomeryAnomalyEvent
class VodomeryEventState(Base):
    __tablename__ = "vodomery_event_state"
    __table_args__ = (
        UniqueConstraint("identifikace", "event_type", "model_version", name="uq_event_state_unique"),
        Index("ix_event_state_lookup","identifikace", "event_type", "model_version"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    consecutive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accumulator: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_event_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    event_start_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_score_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)




# pomocná tabulka pro VodomeryAnomalyEvent
class VodomeryEventEngineState(Base):
    __tablename__ = "vodomery_event_engine_state"
    __table_args__ = {"schema": "monitoring"}

    id: Mapped[int] = mapped_column(primary_key=True)
    model_version: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    last_score_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=text("now()"), nullable=False)


