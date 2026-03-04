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
    __table_args__ = {'schema': 'qgis'}

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


