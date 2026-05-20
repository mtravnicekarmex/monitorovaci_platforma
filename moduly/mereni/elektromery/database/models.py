from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Text, Float, Boolean, BigInteger, Integer, Numeric, DateTime, func, Index, \
    UniqueConstraint, text, CheckConstraint
from geoalchemy2 import Geometry
from typing import List



class Base(DeclarativeBase):
    pass



# areálové elektroměry monitoring na MS
class Elektromer_areal_Zarizeni(Base):
    __tablename__ = 'Zarizeni_elektromery'
    __table_args__ = {'schema': 'dbo'}

    identifikace: Mapped[str] = mapped_column(String(250), primary_key=True, nullable=False, unique=True)
    seriove_cislo: Mapped[int] = mapped_column(BigInteger, nullable=True)
    softlink_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    EAN: Mapped[int] = mapped_column(BigInteger, nullable=True)
    pozice: Mapped[str] = mapped_column(String(250), nullable=True)
    podruzny: Mapped[str] = mapped_column(String(250), nullable=True)
    mistnost: Mapped[str] = mapped_column(String(250), nullable=True)
    umisteni: Mapped[str] = mapped_column(String(250), nullable=True)
    napaji: Mapped[str] = mapped_column(String(250), nullable=True)
    koncovy_odberatel: Mapped[str] = mapped_column(String(250), nullable=True)
    platnost_cejchu: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    jistic: Mapped[str] = mapped_column(String(250), nullable=True)
    typ_merice: Mapped[str] = mapped_column(String(250), nullable=True)
    rozvadec: Mapped[str] = mapped_column(String(250), nullable=True)
    typ_tarifu: Mapped[str] = mapped_column(String(250), nullable=True)
    platnost_od: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    platnost_do: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    plomb: Mapped[str] = mapped_column(String(250), nullable=True)
    mis_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    met_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    foto: Mapped[str] = mapped_column(String(550), nullable=True)

    # Relationships

    mereni: Mapped[List["Elektromer_areal_Mereni"]] = relationship("Elektromer_areal_Mereni", back_populates="zarizeni")

    def __repr__(self) -> str:
        return f"{self.identifikace} - {self.seriove_cislo} - {self.EAN} - {self.platnost_cejchu}"






# areálové elektroměry měření monitoring na MS
class Elektromer_areal_Mereni(Base):
    __tablename__ = 'Mereni_elektromery'
    __table_args__ = {'schema': 'dbo'}

    recid: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, nullable=False)
    identifikace: Mapped[str] = mapped_column(String(250), ForeignKey('dbo.Zarizeni_elektromery.identifikace'),nullable=True)
    seriove_cislo: Mapped[int] = mapped_column(BigInteger, nullable=True)
    vt: Mapped[float] = mapped_column(nullable=True)
    nt: Mapped[float] = mapped_column(nullable=True)
    total: Mapped[float] = mapped_column(nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    softlink_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    vt_var_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    nt_var_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    total_var_id: Mapped[int] = mapped_column(BigInteger, nullable=True)


    # Relationships

    zarizeni: Mapped["Elektromer_areal_Zarizeni"] = relationship("Elektromer_areal_Zarizeni", back_populates="mereni")

    def __repr__(self) -> str:
        return f"{self.date} - {self.identifikace} - {self.total}"


class Mereni_elektromery(Base):
    __tablename__ = "Mereni_elektromery_vse"
    __table_args__ = (
        UniqueConstraint("identifikace", "date", "zdroj", name="uq_ele_vse_ident_date_zdroj"),
        UniqueConstraint("source_recid", "zdroj", name="uq_ele_vse_source_recid_zdroj"),
        Index("ix_ele_vse_ident_interval_slot", "identifikace", "interval_minutes", "day_of_week", "slot"),
        Index("ix_ele_vse_ident_date", "identifikace", "date"),
        Index("ix_ele_vse_date", "date"),
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

    def __repr__(self) -> str:
        return f"{self.date} - {self.identifikace} - {self.zdroj} - {self.delta}"


# areálové elektroměry QGIS na PG
class Elektromer_areal_Zarizeni_QGIS(Base):
    __tablename__ = 'elektroměry'
    __table_args__ = {'schema': 'evidence'}

    identifikace: Mapped[str] = mapped_column(String(250), primary_key=True, nullable=False, unique=True)
    geom: Mapped[Geometry] = mapped_column(Geometry(geometry_type='POINT', srid=5514, spatial_index=True), nullable=True)
    seriove_cislo: Mapped[int] = mapped_column(BigInteger, nullable=True)
    softlink_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    EAN: Mapped[int] = mapped_column(BigInteger, nullable=True)
    pozice: Mapped[str] = mapped_column(String(250), nullable=True)
    podruzny: Mapped[str] = mapped_column(String(250), nullable=True)
    mistnost: Mapped[str] = mapped_column(String(250), nullable=True)
    umisteni: Mapped[str] = mapped_column(String(250), nullable=True)
    napaji: Mapped[str] = mapped_column(String(250), nullable=True)
    koncovy_odberatel: Mapped[str] = mapped_column(String(250), nullable=True)
    platnost_cejchu: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    jistic: Mapped[str] = mapped_column(String(250), nullable=True)
    typ_merice: Mapped[str] = mapped_column(String(250), nullable=True)
    rozvadec: Mapped[str] = mapped_column(String(250), nullable=True)
    typ_tarifu: Mapped[str] = mapped_column(String(250), nullable=True)
    platnost_od: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    platnost_do: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    plomb: Mapped[str] = mapped_column(String(250), nullable=True)
    mis_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    met_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    foto: Mapped[str] = mapped_column(String(550), nullable=True)


    def __repr__(self) -> str:
        return f"{self.identifikace} - {self.seriove_cislo} - {self.EAN} - {self.platnost_cejchu}"










