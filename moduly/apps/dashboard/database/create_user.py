from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.database.db_init import ensure_dashboard_tables
from moduly.apps.dashboard.database.users import upsert_user


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
    seznam_zarizeni = [item.strip() for item in args.zarizeni.split(",") if item.strip()]
    dostupne_sekce = [item.strip() for item in args.sekce.split(",") if item.strip()] or None
    dostupne_stranky = [item.strip() for item in args.stranky.split(",") if item.strip()] or None

    upsert_user(
        username=args.username.strip(),
        password=args.password,
        email=args.email.strip() or None,
        dostupne_sekce=dostupne_sekce,
        dostupne_stranky=dostupne_stranky,
        seznam_zarizeni=seznam_zarizeni,
        is_admin=args.admin,
        is_active=not args.inactive,
    )
    print(f"Uzivatel '{args.username}' byl ulozen.")


if __name__ == "__main__":
    main()
