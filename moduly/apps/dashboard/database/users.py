from __future__ import annotations

from dataclasses import dataclass
import json

from app.time_utils import utc_now_naive
from core.db.connect import get_session_pg
from moduly.apps.dashboard.database.models import Streamlit_Users
from moduly.apps.dashboard.navigation_config import (
    get_default_page_keys,
    get_default_section_keys,
    normalize_page_keys,
    normalize_section_keys,
)
from moduly.apps.dashboard.security import (
    hash_password,
    password_hash_needs_rehash,
    validate_password,
    verify_password,
)


DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$600000$dashboard-login-timing-padding$"
    "a8dc438ae9510ef7e289eb4eaca4d026e7171a890cc22798a8330fdda411a75a"
)


@dataclass(frozen=True)
class UserAuthenticationResult:
    user: Streamlit_Users | None
    reason_category: str
    is_admin_account: bool


def any_users_exist() -> bool:
    session = get_session_pg()
    try:
        return session.query(Streamlit_Users).first() is not None
    finally:
        session.close()


def get_user(username: str) -> Streamlit_Users | None:
    session = get_session_pg()
    try:
        user = session.get(Streamlit_Users, username)
        if user is None:
            return None
        session.expunge(user)
        return user
    finally:
        session.close()


def list_users() -> list[dict[str, object]]:
    session = get_session_pg()
    try:
        rows = (
            session.query(Streamlit_Users)
            .order_by(Streamlit_Users.uzivatel)
            .all()
        )
        return [
            {
                "uzivatel": row.uzivatel,
                "email": row.email,
                "dostupne_sekce": resolve_user_sections(row),
                "dostupne_stranky": resolve_user_pages(row),
                "seznam_zarizeni": row.get_seznam_zarizeni(),
                "is_active": row.is_active,
                "is_admin": row.is_admin,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "last_login_at": row.last_login_at,
            }
            for row in rows
        ]
    finally:
        session.close()


def count_active_admin_users(*, exclude_username: str | None = None) -> int:
    session = get_session_pg()
    try:
        query = session.query(Streamlit_Users).filter(
            Streamlit_Users.is_admin.is_(True),
            Streamlit_Users.is_active.is_(True),
        )
        if exclude_username:
            query = query.filter(Streamlit_Users.uzivatel != exclude_username)
        return int(query.count())
    finally:
        session.close()


def authenticate_user(username: str, password: str) -> Streamlit_Users | None:
    return authenticate_user_with_result(username, password).user


def authenticate_user_with_result(
    username: str,
    password: str,
) -> UserAuthenticationResult:
    session = get_session_pg()
    try:
        user = session.get(Streamlit_Users, username)
        password_hash = user.heslo if user is not None else DUMMY_PASSWORD_HASH
        password_matches = verify_password(password, password_hash)
        if user is None:
            return UserAuthenticationResult(
                user=None,
                reason_category="unknown_account",
                is_admin_account=False,
            )
        if not user.is_active:
            return UserAuthenticationResult(
                user=None,
                reason_category="inactive_account",
                is_admin_account=bool(getattr(user, "is_admin", False)),
            )
        if not password_matches:
            return UserAuthenticationResult(
                user=None,
                reason_category="invalid_password",
                is_admin_account=bool(getattr(user, "is_admin", False)),
            )

        if password_hash_needs_rehash(user.heslo):
            user.heslo = hash_password(password)
            session.commit()
        session.expunge(user)
        return UserAuthenticationResult(
            user=user,
            reason_category="authenticated",
            is_admin_account=bool(getattr(user, "is_admin", False)),
        )
    finally:
        session.close()


def resolve_user_sections(user: Streamlit_Users) -> list[str]:
    if user.is_admin:
        return get_default_section_keys(is_admin=True, allowed_devices=())

    raw_sections = user.get_dostupne_sekce()
    if raw_sections is None:
        return get_default_section_keys(is_admin=False, allowed_devices=user.get_seznam_zarizeni())
    return normalize_section_keys(raw_sections)


def resolve_user_pages(user: Streamlit_Users, effective_sections: list[str] | None = None) -> list[str]:
    resolved_sections = effective_sections if effective_sections is not None else resolve_user_sections(user)

    if user.is_admin:
        return get_default_page_keys(is_admin=True, section_keys=resolved_sections, allowed_devices=())

    raw_pages = user.get_dostupne_stranky()
    if raw_pages is None:
        return get_default_page_keys(
            is_admin=False,
            section_keys=resolved_sections,
            allowed_devices=user.get_seznam_zarizeni(),
        )
    return normalize_page_keys(raw_pages, allowed_section_keys=resolved_sections)


def verify_user_password(username: str, password: str) -> bool:
    session = get_session_pg()
    try:
        user = session.get(Streamlit_Users, username)
        if user is None or not user.is_active:
            return False
        return verify_password(password, user.heslo)
    finally:
        session.close()


def update_last_login(username: str, login_time) -> None:
    session = get_session_pg()
    try:
        user = session.get(Streamlit_Users, username)
        if user is None:
            return
        user.last_login_at = login_time or utc_now_naive()
        session.commit()
    finally:
        session.close()


def update_password(username: str, new_password: str) -> None:
    validate_password(new_password, username=username)
    session = get_session_pg()
    try:
        user = session.get(Streamlit_Users, username)
        if user is None:
            raise ValueError("Uzivatel neexistuje.")
        user.heslo = hash_password(new_password)
        user.token_version = int(user.token_version or 0) + 1
        session.commit()
    finally:
        session.close()


def update_email(username: str, new_email: str | None) -> None:
    session = get_session_pg()
    try:
        user = session.get(Streamlit_Users, username)
        if user is None:
            raise ValueError("Uzivatel neexistuje.")
        user.email = new_email.strip() if new_email else None
        session.commit()
    finally:
        session.close()


def upsert_user(
    username: str,
    password: str | None,
    email: str | None = None,
    dostupne_sekce: list[str] | None = None,
    dostupne_stranky: list[str] | None = None,
    seznam_zarizeni: list[str] | None = None,
    is_admin: bool = False,
    is_active: bool = True,
) -> None:
    if password is not None:
        validate_password(password, username=username)

    session = get_session_pg()
    try:
        user = session.get(Streamlit_Users, username)
        resolved_devices = list(seznam_zarizeni or [])
        resolved_sections = normalize_section_keys(
            dostupne_sekce
            if dostupne_sekce is not None
            else (
                resolve_user_sections(user)
                if user is not None
                else get_default_section_keys(is_admin=is_admin, allowed_devices=resolved_devices)
            )
        )
        resolved_pages = normalize_page_keys(
            dostupne_stranky
            if dostupne_stranky is not None
            else (
                resolve_user_pages(user, resolved_sections)
                if user is not None
                else get_default_page_keys(
                    is_admin=is_admin,
                    section_keys=resolved_sections,
                    allowed_devices=resolved_devices,
                )
            ),
            allowed_section_keys=resolved_sections,
        )
        serialized_devices = json.dumps(resolved_devices, ensure_ascii=True)
        serialized_sections = json.dumps(resolved_sections, ensure_ascii=True)
        serialized_pages = json.dumps(resolved_pages, ensure_ascii=True)

        if user is None:
            if not password:
                raise ValueError("Pro noveho uzivatele je heslo povinne.")

            user = Streamlit_Users(
                uzivatel=username,
                email=email.strip() if email else None,
                heslo=hash_password(password),
                dostupne_sekce=serialized_sections,
                dostupne_stranky=serialized_pages,
                seznam_zarizeni=serialized_devices,
                is_admin=is_admin,
                is_active=is_active,
            )
            session.add(user)
        else:
            if password:
                user.heslo = hash_password(password)
                user.token_version = int(user.token_version or 0) + 1
            user.email = email.strip() if email else None
            user.dostupne_sekce = serialized_sections
            user.dostupne_stranky = serialized_pages
            user.seznam_zarizeni = serialized_devices
            user.is_admin = is_admin
            user.is_active = is_active

        session.commit()
    finally:
        session.close()


def delete_user(username: str) -> None:
    session = get_session_pg()
    try:
        user = session.get(Streamlit_Users, username)
        if user is None:
            return
        session.delete(user)
        session.commit()
    finally:
        session.close()


def revoke_user_tokens(username: str) -> int | None:
    session = get_session_pg()
    try:
        user = session.get(Streamlit_Users, username)
        if user is None:
            return None
        user.token_version = int(user.token_version or 0) + 1
        session.commit()
        return int(user.token_version)
    finally:
        session.close()
