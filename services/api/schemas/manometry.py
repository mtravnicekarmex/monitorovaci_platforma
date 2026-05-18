from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class ManometryDeviceListResponse(BaseModel):
    total: int
    devices: list[str]


class ManometryMeasurementSeriesRow(BaseModel):
    date: datetime
    identifikace: str
    seriove_cislo: str | None = None
    hodnota: float
    platne: bool | None = None
    zdroj: str | None = None
    source_date: datetime | None = None
    time_utc: datetime | None = None
    time_basis: str | None = None
    source_timezone: str | None = None
    source_utc_offset_minutes: int | None = None
    time_fold: int | None = None
    timestamp_position: str | None = None


class ManometryMeasurementSeriesResponse(BaseModel):
    identifikace: str
    start_date: date
    end_date: date
    total: int
    rows: list[ManometryMeasurementSeriesRow]


class ManometryDeviceDetail(BaseModel):
    identifikace: str
    seriove_cislo: str | None = None
    objekt: str | None = None
    mistnost: str | None = None
    patro: str | None = None
    vetev: str | None = None
    foto: str | None = None
    measurement_count: int = 0
    valid_measurement_count: int = 0
    first_measurement_at: datetime | None = None
    last_measurement_at: datetime | None = None
    min_pressure: float | None = None
    min_pressure_at: datetime | None = None
    max_pressure: float | None = None
    max_pressure_at: datetime | None = None


class ManometryDeviceDetailResponse(BaseModel):
    identifikace: str
    found: bool
    device: ManometryDeviceDetail | None = None
