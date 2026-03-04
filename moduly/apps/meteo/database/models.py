from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Text, Float, Boolean, BigInteger, Integer, Numeric, DateTime, func, Index, \
    UniqueConstraint, text, CheckConstraint
from geoalchemy2 import Geometry
from typing import List



class Base(DeclarativeBase):
    pass





# ukládá historii Meteo údajů z místa areálu
class MeteoHourly(Base):
    __tablename__ = "meteo_hourly"
    __table_args__ = (
        Index("ix_meteo_hourly_datetime_hour", "datetime_hour"),

        {"schema": "monitoring"},
    )

    # 🕒 Hodina v UTC – primární klíč
    datetime_hour: Mapped[datetime] = mapped_column(DateTime(timezone=False), primary_key=True, nullable=False)

    # 🌡 Teplota
    temperature: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False) # -99.99 až 999.99 °C (bezpečná rezerva)
    apparent_temperature: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True)

    # 💧 Vlhkost & srážky
    relative_humidity: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True) # %
    precipitation: Mapped[float] = mapped_column(Numeric(6, 2), nullable=True) # mm
    snowfall: Mapped[float] = mapped_column(Numeric(6, 2), nullable=True) # cm

    # ☁ Oblačnost & vítr
    cloud_cover: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True)  # %
    wind_speed: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True)  # m/s

    # 🔵 Tlak
    surface_pressure: Mapped[float] = mapped_column(Numeric(7, 2), nullable=True) # hPa

    # 🔥 Derived energetické metriky
    heating_degree_hours: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    cooling_degree_hours: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    # 📅 Audit
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False)
