from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SmartFuelPassRelace(Base):
    __tablename__ = "smartfuelpass_relace"
    __table_args__ = {"schema": "monitoring"}

    id_relace: Mapped[str] = mapped_column(String(64), primary_key=True, nullable=False)
    kwh: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    tarif: Mapped[str | None] = mapped_column(String(255), nullable=True)
    battery_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suma: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    lokace: Mapped[str] = mapped_column(String(255), nullable=False)
    rychlost_nabijeni: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
