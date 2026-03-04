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
    __table_args__ = {'schema': 'qgis'}

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





