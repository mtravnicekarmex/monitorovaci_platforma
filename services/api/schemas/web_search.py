from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WebSearchHit(BaseModel):
    vyraz: str
    snippet: str | None = None
    odkaz: str | None = None


class WebSearchPreviewRequest(BaseModel):
    url: str = Field(min_length=1, max_length=550)
    expressions: list[str] = Field(default_factory=list)


class WebSearchPreviewResponse(BaseModel):
    url: str
    total: int
    hits: list[WebSearchHit]


class WebSearchMonitorRecord(BaseModel):
    id: int
    url: str
    email: str
    expressions: list[str]
    last_run: datetime | None = None
    created: datetime
    results_count: int = 0


class WebSearchMonitorsResponse(BaseModel):
    total: int
    rows: list[WebSearchMonitorRecord]


class WebSearchMonitorUpsertRequest(BaseModel):
    url: str = Field(min_length=1, max_length=550)
    email: str = Field(min_length=1, max_length=250)
    expressions: list[str] = Field(default_factory=list)


class WebSearchMonitorUpsertResponse(BaseModel):
    monitor: WebSearchMonitorRecord
    created: bool
    added_expressions: list[str] = Field(default_factory=list)


class WebSearchResultRow(BaseModel):
    id: int
    monitor_id: int
    monitor_url: str | None = None
    url: str
    vyraz: str
    snippet: str | None = None
    odkaz: str | None = None
    datum: datetime
    notified: bool


class WebSearchResultsResponse(BaseModel):
    total: int
    rows: list[WebSearchResultRow]
