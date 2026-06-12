from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class UsersExistResponse(BaseModel):
    users_exist: bool


class UserProfileResponse(BaseModel):
    username: str
    email: str | None = None
    is_admin: bool
    is_active: bool
    allowed_sections: list[str]
    allowed_pages: list[str]
    allowed_devices: list[str]
    last_login_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserProfileResponse


class EmailUpdateRequest(BaseModel):
    email: str | None = Field(default=None, max_length=250)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)
