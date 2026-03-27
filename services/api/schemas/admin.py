from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AdminDeviceOptionsResponse(BaseModel):
    total: int
    devices: list[str]


class AdminUserRecord(BaseModel):
    username: str
    email: str | None = None
    available_sections: list[str]
    available_pages: list[str]
    device_ids: list[str]
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class AdminUsersResponse(BaseModel):
    total: int
    users: list[AdminUserRecord]


class AdminUserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)
    email: str | None = Field(default=None, max_length=250)
    available_sections: list[str] = Field(default_factory=list)
    available_pages: list[str] = Field(default_factory=list)
    device_ids: list[str] = Field(default_factory=list)
    is_active: bool = True
    is_admin: bool = False


class AdminUserUpdateRequest(BaseModel):
    password: str | None = Field(default=None, min_length=1, max_length=1024)
    email: str | None = Field(default=None, max_length=250)
    available_sections: list[str] | None = None
    available_pages: list[str] | None = None
    device_ids: list[str] | None = None
    is_active: bool | None = None
    is_admin: bool | None = None
