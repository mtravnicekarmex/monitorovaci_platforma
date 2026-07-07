from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SmartFuelPassRelace(Base):
    __tablename__ = "smartfuelpass_relace"
    __table_args__ = (
        Index("ix_smartfuelpass_relace_started_at_utc", "started_at_utc"),
        Index("ix_smartfuelpass_relace_ended_at_utc", "ended_at_utc"),
        {"schema": "monitoring"},
    )

    id_relace: Mapped[str] = mapped_column(String(64), primary_key=True, nullable=False)
    kwh: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    tarif: Mapped[str | None] = mapped_column(String(255), nullable=True)
    battery_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suma: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    connector_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    source_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    source_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    started_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_basis: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_utc_offset_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ended_utc_offset_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_time_fold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ended_time_fold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp_position: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lokace: Mapped[str] = mapped_column(String(255), nullable=False)
    rychlost_nabijeni: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
