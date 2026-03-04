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
    softlink_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    vt_var_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    nt_var_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    total_var_id: Mapped[int] = mapped_column(BigInteger, nullable=True)


    # Relationships

    zarizeni: Mapped["Elektromer_areal_Zarizeni"] = relationship("Elektromer_areal_Zarizeni", back_populates="mereni")

    def __repr__(self) -> str:
        return f"{self.date} - {self.identifikace} - {self.total}"




# areálové elektroměry QGIS na PG
class Elektromer_areal_Zarizeni_QGIS(Base):
    __tablename__ = 'elektroměry'
    __table_args__ = {'schema': 'qgis'}

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










