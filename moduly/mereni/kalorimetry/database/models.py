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
    plynomer: Mapped[str] = mapped_column(String(250), nullable=True)
    koncovy_odberatel: Mapped[str] = mapped_column(String(250), nullable=True)
    platnost_cejchu: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
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
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)

    # Relationships

    zarizeni: Mapped["Kalorimetr_areal_Zarizeni"] = relationship("Kalorimetr_areal_Zarizeni", back_populates="mereni")

    def __repr__(self) -> str:
        return f"{self.date} - {self.identifikace} - {self.objem}"




class Kalorimetr_areal_Zarizeni_QGIS(Base):
    __tablename__ = 'kalorimetry'
    __table_args__ = {'schema': 'qgis'}

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
    plynomer: Mapped[str] = mapped_column(String(250), nullable=True)
    koncovy_odberatel: Mapped[str] = mapped_column(String(250), nullable=True)
    platnost_cejchu: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    poznamka_kalorimetry: Mapped[str] = mapped_column(String(250), nullable=True)
    foto: Mapped[str] = mapped_column(String(550), nullable=True)


    def __repr__(self) -> str:
        return f"{self.identifikace} - {self.seriove_cislo}"




