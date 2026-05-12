from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.time_utils import utc_now_naive
from moduly.apps.dashboard.database.models import Streamlit_Users
from moduly.apps.dashboard.database.users import (
    any_users_exist,
    authenticate_user,
    get_user,
    revoke_user_tokens,
    resolve_user_pages,
    resolve_user_sections,
    update_email,
    update_last_login,
    update_password,
    verify_user_password,
)
from moduly.apps.dashboard.navigation_config import get_page_definition, get_section_definition


class AuthenticationError(ValueError):
    """Raised when username/password authentication fails."""


class AuthorizationError(ValueError):
    """Raised when the current user cannot access a protected resource."""


class UserUpdateError(ValueError):
    """Raised when a user profile update request is invalid."""


@dataclass(frozen=True)
class DashboardUserContext:
    username: str
    email: str | None
    is_admin: bool
    is_active: bool
    allowed_sections: tuple[str, ...]
    allowed_pages: tuple[str, ...]
    allowed_devices: tuple[str, ...]
    last_login_at: datetime | None
    token_version: int

    def to_profile_dict(self) -> dict[str, object]:
        return {
            "username": self.username,
            "email": self.email,
            "is_admin": self.is_admin,
            "is_active": self.is_active,
            "allowed_sections": list(self.allowed_sections),
            "allowed_pages": list(self.allowed_pages),
            "allowed_devices": list(self.allowed_devices),
            "last_login_at": self.last_login_at,
        }


def build_user_context(
    user: Streamlit_Users,
    *,
    last_login_override: datetime | None = None,
) -> DashboardUserContext:
    allowed_devices = tuple(user.get_seznam_zarizeni())
    allowed_sections = tuple(resolve_user_sections(user))
    allowed_pages = tuple(resolve_user_pages(user, list(allowed_sections)))
    return DashboardUserContext(
        username=user.uzivatel,
        email=user.email,
        is_admin=bool(user.is_admin),
        is_active=bool(user.is_active),
        allowed_sections=allowed_sections,
        allowed_pages=allowed_pages,
        allowed_devices=allowed_devices,
        last_login_at=last_login_override if last_login_override is not None else user.last_login_at,
        token_version=int(user.token_version or 0),
    )


def authenticate_dashboard_user(username: str, password: str) -> DashboardUserContext:
    user = authenticate_user(username.strip(), password)
    if user is None:
        raise AuthenticationError("Neplatne prihlasovaci udaje.")

    login_time = utc_now_naive()
    update_last_login(user.uzivatel, login_time)
    return build_user_context(user, last_login_override=login_time)


def dashboard_users_exist() -> bool:
    return any_users_exist()


def get_dashboard_user_context(username: str) -> DashboardUserContext | None:
    user = get_user(username.strip())
    if user is None or not user.is_active:
        return None
    return build_user_context(user)


def require_section_access(user_context: DashboardUserContext, section_key: str) -> None:
    section = get_section_definition(section_key)
    if section is None:
        raise AuthorizationError("Neznama sekce dashboardu.")

    if user_context.is_admin:
        return

    if section_key not in user_context.allowed_sections:
        raise AuthorizationError("Na tuto sekci nemate opravneni.")

    if section.requires_device_permissions and not user_context.allowed_devices:
        raise AuthorizationError("Uzivateli nejsou prirazena zadna zarizeni pro tuto sekci.")


def require_page_access(user_context: DashboardUserContext, page_key: str) -> None:
    page = get_page_definition(page_key)
    if page is None:
        raise AuthorizationError("Neznama stranka dashboardu.")

    if user_context.is_admin:
        return

    if page.admin_only:
        raise AuthorizationError("Tato stranka je dostupna pouze adminovi.")

    if page.section_key is not None:
        require_section_access(user_context, page.section_key)
    if page.configurable and page.key not in user_context.allowed_pages:
        raise AuthorizationError("Na tuto stranku nemate opravneni.")


def require_device_access(user_context: DashboardUserContext, identifikace: str) -> None:
    if user_context.is_admin:
        return
    if identifikace not in user_context.allowed_devices:
        raise AuthorizationError("Na toto zarizeni nemate opravneni.")


def update_dashboard_user_email(username: str, email: str | None) -> DashboardUserContext:
    update_email(username, email)
    user_context = get_dashboard_user_context(username)
    if user_context is None:
        raise UserUpdateError("Uzivatel neexistuje nebo je neaktivni.")
    return user_context


def change_dashboard_user_password(
    username: str,
    current_password: str,
    new_password: str,
) -> None:
    if not verify_user_password(username, current_password):
        raise AuthenticationError("Soucasne heslo neni spravne.")
    if len(new_password) < 8:
        raise UserUpdateError("Nove heslo musi mit alespon 8 znaku.")
    update_password(username, new_password)


def logout_dashboard_user(username: str) -> None:
    revoke_user_tokens(username)
