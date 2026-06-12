from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.database.db_init import ensure_dashboard_tables
from moduly.apps.dashboard.database.users import get_user, upsert_user
from services.api.core.auth_audit import auth_audit_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vytvori nebo aktualizuje uzivatele dashboardu.")
    parser.add_argument("--username", required=True, help="Login uzivatele")
    parser.add_argument("--email", default="", help="Email uzivatele")
    parser.add_argument("--password", required=True, help="Heslo v otevrene podobe; ulozi se jako hash")
    parser.add_argument(
        "--zarizeni",
        default="",
        help="Carkou oddeleny seznam identifikaci zarizeni; prazdne pro zadny explicitni seznam",
    )
    parser.add_argument(
        "--sekce",
        default="",
        help="Carkou oddeleny seznam dostupnych sekci; prazdne pouzije vychozi chovani",
    )
    parser.add_argument(
        "--stranky",
        default="",
        help="Carkou oddeleny seznam dostupnych stranek; prazdne pouzije vychozi chovani",
    )
    parser.add_argument("--admin", action="store_true", help="Uzivatel bude admin")
    parser.add_argument("--inactive", action="store_true", help="Uzivatel bude neaktivni")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_dashboard_tables()
    username = args.username.strip()
    existing_user = get_user(username)
    seznam_zarizeni = [item.strip() for item in args.zarizeni.split(",") if item.strip()]
    dostupne_sekce = [item.strip() for item in args.sekce.split(",") if item.strip()] or None
    dostupne_stranky = [item.strip() for item in args.stranky.split(",") if item.strip()] or None

    upsert_user(
        username=username,
        password=args.password,
        email=args.email.strip() or None,
        dostupne_sekce=dostupne_sekce,
        dostupne_stranky=dostupne_stranky,
        seznam_zarizeni=seznam_zarizeni,
        is_admin=args.admin,
        is_active=not args.inactive,
    )
    actor = f"local:{getpass.getuser()}"
    if existing_user is None:
        auth_audit_service.record_security_event(
            event_type="account_created",
            result="success",
            reason="local_cli",
            actor_username=actor,
            target_username=username,
            details={
                "is_admin": bool(args.admin),
                "is_active": not args.inactive,
            },
        )
    else:
        changed_fields = ["password"]
        if bool(existing_user.is_admin) != bool(args.admin):
            changed_fields.append("is_admin")
        if bool(existing_user.is_active) != (not args.inactive):
            changed_fields.append("is_active")
        auth_audit_service.record_security_event(
            event_type="account_updated",
            result="success",
            reason="local_cli",
            actor_username=actor,
            target_username=username,
            details={"changed_fields": changed_fields},
        )
        auth_audit_service.record_security_event(
            event_type="password_change",
            result="success",
            reason="local_cli_reset",
            actor_username=actor,
            target_username=username,
        )
        auth_audit_service.record_security_event(
            event_type="token_revocation",
            result="success",
            reason="local_cli_password_reset",
            actor_username=actor,
            target_username=username,
        )
        if bool(existing_user.is_admin) != bool(args.admin):
            auth_audit_service.record_security_event(
                event_type="role_change",
                result="success",
                reason="local_cli",
                actor_username=actor,
                target_username=username,
                details={
                    "previous_is_admin": bool(existing_user.is_admin),
                    "is_admin": bool(args.admin),
                },
            )
        if bool(existing_user.is_active) != (not args.inactive):
            auth_audit_service.record_security_event(
                event_type="account_activation_change",
                result="success",
                reason=(
                    "account_activated"
                    if not args.inactive
                    else "account_deactivated"
                ),
                actor_username=actor,
                target_username=username,
                details={
                    "previous_is_active": bool(existing_user.is_active),
                    "is_active": not args.inactive,
                },
            )
    print(f"Uzivatel '{args.username}' byl ulozen.")


if __name__ == "__main__":
    main()
