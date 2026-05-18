from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Text, Float, Boolean, BigInteger, Integer, Numeric, DateTime, func, Index, \
    UniqueConstraint, text, CheckConstraint
from geoalchemy2 import Geometry
from typing import List



class Base(DeclarativeBase):
    pass




# areálové manometry monitoring na MS
class Manometr_areal_Zarizeni(Base):
    __tablename__ = 'Zarizeni_manometry'
    __table_args__ = {'schema': 'dbo'}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, nullable=False)
    seriove_cislo: Mapped[str] = mapped_column(nullable=False)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=True, unique=True)
    objekt: Mapped[str] = mapped_column(String(10), nullable=True)
    mistnost: Mapped[str] = mapped_column(String(10), nullable=True)
    patro: Mapped[str] = mapped_column(String(10), nullable=True)
    vetev: Mapped[str] = mapped_column(String(30), nullable=True)
    foto: Mapped[str] = mapped_column(String(550), nullable=True)

    # Relationships

    mereni: Mapped[List["Mereni_manometry"]] = relationship("Mereni_manometry", back_populates="zarizeni")

    def __repr__(self) -> str:
        return f"{self.identifikace} - {self.seriove_cislo}"




# areálové manometry měření monitoring na MS
class Mereni_manometry(Base):
    __tablename__ = 'Mereni_manometry'
    __table_args__ = {'schema': 'dbo'}

    recid: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, nullable=False)
    identifikace: Mapped[str] = mapped_column(ForeignKey('dbo.Zarizeni_manometry.identifikace'), nullable=True)
    seriove_cislo: Mapped[str] = mapped_column(String(250), nullable=False)
    hodnota: Mapped[float] = mapped_column(nullable=True)
    platne: Mapped[bool] = mapped_column(nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)

    # Relationships

    zarizeni: Mapped["Manometr_areal_Zarizeni"] = relationship("Manometr_areal_Zarizeni", back_populates="mereni")

    def __repr__(self) -> str:
        return f"{self.date} - {self.identifikace} - {self.hodnota}"





# areálové manometry QGIS na PG
class Manometr_areal_Zarizeni_QGIS(Base):
    __tablename__ = 'manometry'
    __table_args__ = {'schema': 'evidence'}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, nullable=False)
    geom: Mapped[Geometry] = mapped_column(Geometry(geometry_type='POINT', srid=5514, spatial_index=True), nullable=True)
    seriove_cislo: Mapped[str] = mapped_column(nullable=False)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=True, unique=True)
    objekt: Mapped[str] = mapped_column(String(10), nullable=True)
    patro: Mapped[str] = mapped_column(String(10), nullable=True)
    mistnost: Mapped[str] = mapped_column(String(10), nullable=True)
    foto: Mapped[str] = mapped_column(String(550), nullable=True)


    def __repr__(self) -> str:
        return f"{self.identifikace} - {self.seriove_cislo}"


# arealove manometry monitoring na PG
class Mereni_manometry_vse(Base):
    __tablename__ = "Mereni_manometry_vse"
    __table_args__ = (
        UniqueConstraint("identifikace", "date", "zdroj", name="uq_manometry_ident_date_zdroj"),
        UniqueConstraint("source_recid", "zdroj", name="uq_manometry_source_recid_zdroj"),
        Index("ix_manometry_ident_date_desc", "identifikace", "date"),
        Index("ix_manometry_date_desc", "date"),
        Index("ix_manometry_vse_time_utc", "time_utc"),
        Index("ix_manometry_vse_ident_time_utc", "identifikace", "time_utc"),
        {"schema": "monitoring"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_recid: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    identifikace: Mapped[str] = mapped_column(String(250), nullable=False)
    seriove_cislo: Mapped[str | None] = mapped_column(String(250), nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    source_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_basis: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_utc_offset_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_fold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp_position: Mapped[str | None] = mapped_column(String(20), nullable=True)
    hodnota: Mapped[float] = mapped_column(Float, nullable=False)
    platne: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    zdroj: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False)





