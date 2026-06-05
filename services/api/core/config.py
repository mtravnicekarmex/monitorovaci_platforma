from __future__ import annotations

from dataclasses import dataclass

from decouple import config


@dataclass(frozen=True)
class ApiSettings:
    title: str
    version: str
    token_secret: str
    token_expiry_minutes: int
    cors_origins: tuple[str, ...]


def _get_required_token_secret() -> str:
    token_secret = config("API_TOKEN_SECRET", default="").strip()
    if not token_secret or token_secret.casefold() == "change-me":
        raise ValueError(
            "API_TOKEN_SECRET musi byt nastaveno v .env nebo v prostredi a nesmi zustat na placeholderu 'change-me'."
        )
    return token_secret


def _get_cors_origins() -> tuple[str, ...]:
    default_origins = (
        "http://127.0.0.1:8001",
        "http://localhost:8001",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
    )
    raw_value = config("API_CORS_ORIGINS", default=",".join(default_origins))
    origins = tuple(
        origin.strip().rstrip("/")
        for origin in str(raw_value).split(",")
        if origin.strip()
    )
    return origins


def get_api_settings() -> ApiSettings:
    return ApiSettings(
        title=config("API_TITLE", default="Monitoring Platform API"),
        version=config("API_VERSION", default="0.1.0"),
        token_secret=_get_required_token_secret(),
        token_expiry_minutes=config("API_TOKEN_EXPIRY_MINUTES", default=480, cast=int),
        cors_origins=_get_cors_origins(),
    )
