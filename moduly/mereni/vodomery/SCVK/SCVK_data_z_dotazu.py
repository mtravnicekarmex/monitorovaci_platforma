import datetime
import random
import time
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List

import requests
from decouple import config
from sqlalchemy import select

from core.db.connect import SessionLocalPG
from moduly.mereni.vodomery.database.models import Vodomer_SCVK_Mereni





""" SČVK data
    Číslo hlavy     Ev. č. OM    Výr. č. vodoměru     Popis
    IOTW-049672     602003694       017021            DOKTOR voda, Folknářská 1246/21
    IOTW-049668     602003779       040202            DOKTOR požární voda, Folknářská 1246/21
    IOTW-049708     681189817       015971            B1 NEWAYS, Benešovská
    IOTW-049698     681041132       005872            HECHT, Benešovská
    IOTW-049674     602009738       005354            GROBÁR, Folknářská
    IOTW-067073     681290535       013445            S1, Folknářská
    IOTW-066996     602003797       091818            Staré město, Nám. 5.května
"""

paths = {
    "SCVK_DP": {
        "oznaceni": "DOKTOR požární voda",
        "odberne misto": "602003779",
        "cislo vodomeru": "040202",
        "cislo hlavy": "IOTW-049668",
        "denni limit": 20,
        "stočné": "ne",
        "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_040202.xlsx",
    },
    "SCVK_DV": {
        "oznaceni": "DOKTOR voda",
        "odberne misto": "602003694",
        "cislo vodomeru": "017021",
        "cislo hlavy": "IOTW-049672",
        "denni limit": 8,
        "stočné": "ne",
        "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_017021.xlsx",
    },
    "SCVK_B1": {
        "oznaceni": "B1 NEWAYS",
        "odberne misto": "681189817",
        "cislo vodomeru": "015971",
        "cislo hlavy": "IOTW-049708",
        "denni limit": 20,
        "stočné": "ano",
        "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_037550.xlsx",
    },
    "SCVK_HE": {
        "oznaceni": "HECHT",
        "odberne misto": "681041132",
        "cislo vodomeru": "005872",
        "cislo hlavy": "IOTW-049698",
        "denni limit": 12,
        "stočné": "ano",
        "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_005872.xlsx",
    },
    "SCVK_GR": {
        "oznaceni": "GROBÁR",
        "odberne misto": "602009738",
        "cislo vodomeru": "005354",
        "cislo hlavy": "IOTW-049674",
        "denni limit": 8,
        "stočné": "ne",
        "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_005354.xlsx",
    },
    "SCVK_S1": {
        "oznaceni": "S1",
        "odberne misto": "681290535",
        "cislo vodomeru": "013445",
        "cislo hlavy": "IOTW-067073",
        "denni limit": 1,
        "stočné": "ano",
    },
    "SCVK_ST": {
        "oznaceni": "Staré město",
        "odberne misto": "602003797",
        "cislo vodomeru": "091818",
        "cislo hlavy": "IOTW-066996",
        "denni limit": 1,
        "stočné": "ano",
    },
}

pocet_vodomeru = len(paths)
seznam_vodomeru = list(paths.keys())



def get_last_db_date(seriove_cislo):
    stmt = (
        select(Vodomer_SCVK_Mereni.date)
        .where(Vodomer_SCVK_Mereni.seriove_cislo == seriove_cislo)
        .order_by(Vodomer_SCVK_Mereni.date.desc())
        .limit(1)
    )

    with SessionLocalPG() as session:
        return session.execute(stmt).scalar_one_or_none()




def SCVK_denni_limit(dotazVodomer: str) -> int:
    return paths[dotazVodomer]["denni limit"]



def _resolve_verify_setting() -> Any:
    # Default: strict TLS verification.
    ca_bundle = config("SCVK_CA_BUNDLE", default="").strip()
    if ca_bundle:
        return ca_bundle

    allow_insecure = config("SCVK_ALLOW_INSECURE_SSL", default=False, cast=bool)
    if allow_insecure:
        print(
            "WARNING: SCVK_ALLOW_INSECURE_SSL=true -> TLS verification is disabled. "
            "Use only for temporary local diagnostics."
        )
        return False

    return True



def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout_seconds: int,
    verify: Any,
    **kwargs: Any,
) -> Any:
    max_attempts = max(config("SCVK_HTTP_MAX_ATTEMPTS", default=5, cast=int), 1)
    backoff_base = config("SCVK_HTTP_BACKOFF_BASE_SECONDS", default=1.5, cast=float)
    backoff_cap = config("SCVK_HTTP_BACKOFF_CAP_SECONDS", default=60.0, cast=float)

    def _compute_retry_after_seconds(response: requests.Response) -> float | None:
        header_value = (response.headers.get("Retry-After") or "").strip()
        if not header_value:
            return None

        if header_value.isdigit():
            return float(header_value)

        try:
            retry_at = parsedate_to_datetime(header_value)
            if retry_at is None:
                return None
            now = datetime.datetime.now(retry_at.tzinfo)
            return max((retry_at - now).total_seconds(), 0.0)
        except (TypeError, ValueError, OverflowError):
            return None

    for attempt in range(1, max_attempts + 1):
        try:
            response = session.request(
                method=method,
                url=url,
                timeout=timeout_seconds,
                verify=verify,
                **kwargs,
            )

            if response.status_code == 429 and attempt < max_attempts:
                retry_after = _compute_retry_after_seconds(response)
                exponential = min(backoff_base * (2 ** (attempt - 1)), backoff_cap)
                delay_seconds = retry_after if retry_after is not None else exponential
                delay_seconds = max(delay_seconds, 0.0) + random.uniform(0.0, 0.4)
                print(
                    f"SČVK API rate limit (429) pro {url}. "
                    f"Retry {attempt}/{max_attempts} za {delay_seconds:.1f}s."
                )
                time.sleep(delay_seconds)
                continue

            if response.status_code in {500, 502, 503, 504} and attempt < max_attempts:
                delay_seconds = min(backoff_base * (2 ** (attempt - 1)), backoff_cap)
                delay_seconds += random.uniform(0.0, 0.4)
                print(
                    f"SČVK API dočasná chyba {response.status_code} pro {url}. "
                    f"Retry {attempt}/{max_attempts} za {delay_seconds:.1f}s."
                )
                time.sleep(delay_seconds)
                continue

            response.raise_for_status()
            return response.json()
        except requests.exceptions.SSLError as exc:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            raise RuntimeError(
                "TLS connection to SČVK failed during certificate verification. "
                f"Current local time is {current_time}. "
                "The certificate chain is reported as expired. "
                "Permanent fix: renew/fix certificate on the server (or TLS-inspecting proxy) "
                "and keep strict verification enabled. Client-side disable-verify is not a "
                "production solution."
            ) from exc
        except requests.exceptions.RequestException as exc:
            if attempt < max_attempts:
                delay_seconds = min(backoff_base * (2 ** (attempt - 1)), backoff_cap)
                delay_seconds += random.uniform(0.0, 0.4)
                print(
                    f"SČVK HTTP chyba pro {url}: {exc}. "
                    f"Retry {attempt}/{max_attempts} za {delay_seconds:.1f}s."
                )
                time.sleep(delay_seconds)
                continue
            raise RuntimeError(f"HTTP request failed for {url}: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError(f"Invalid JSON response from {url}") from exc

    raise RuntimeError(f"HTTP request failed for {url} after {max_attempts} attempts.")



def _extract_token(login_payload: Dict[str, Any]) -> str:
    if not isinstance(login_payload, dict) or not login_payload:
        raise RuntimeError("Login response is empty or not a JSON object.")

    # Prefer explicit token keys if present.
    for key in ("token", "access_token", "jwt", "id_token"):
        value = login_payload.get(key)
        if isinstance(value, str) and value.strip():
            return f"Bearer {value}"

    # Fallback to first non-empty string value (keeps compatibility with original API shape).
    for value in login_payload.values():
        if isinstance(value, str) and value.strip():
            return f"Bearer {value}"

    raise RuntimeError("No usable token found in login response.")



def SCVK_dotaz(dotazVodomer: str) -> List[Dict[str, Any]]:
    if dotazVodomer not in paths:
        raise KeyError(
            f"Neznámý vodoměr '{dotazVodomer}'. Povolené hodnoty: {', '.join(paths.keys())}"
        )

    scvk_vodomer = paths[dotazVodomer]["cislo hlavy"]
    scvk_cislo_vodomeru = paths[dotazVodomer]["cislo vodomeru"]
    scvk_popis = paths[dotazVodomer]["oznaceni"]

    print(f"SČVK {scvk_cislo_vodomeru} - {scvk_popis}")

    odKdy = get_last_db_date(scvk_cislo_vodomeru)
    if odKdy is None:
        # Initial sync fallback when DB has no history yet.
        bootstrap_days = config("SCVK_BOOTSTRAP_DAYS", default=7, cast=int)
        odKdy = datetime.datetime.now() - datetime.timedelta(days=bootstrap_days)
        print(
            f"V DB není předchozí záznam pro vodoměr {scvk_cislo_vodomeru}. "
            f"Používám bootstrap okno {bootstrap_days} dní."
        )
    TsOdKdy = int(datetime.datetime.timestamp(odKdy) * 1000)
    print(odKdy)

    ted = datetime.datetime.now()
    TsDoKdy = int(datetime.datetime.timestamp(ted) * 1000)
    print(ted.strftime("%Y-%m-%d %H:%M:%S"))

    login_url = config("URL_SCVK")
    api_url = config("SCVK_API_URL", default="https://sm.scvoda.cz/api")
    timeout_seconds = config("REQUEST_TIMEOUT_SECONDS", default=20, cast=int)
    verify = _resolve_verify_setting()

    login_data = {
        "username": config("USERNAME_SCVK"),
        "password": config("PASSWORD_SCVK"),
    }

    with requests.Session() as session:
        login_payload = _request_json(
            session,
            "POST",
            login_url,
            timeout_seconds=timeout_seconds,
            verify=verify,
            json=login_data,
        )

        token = _extract_token(login_payload)

        headers = {"Authorization": token}
        params = {
            "tsFrom": TsOdKdy,
            "deviceId": scvk_vodomer,
            "tsUntil": TsDoKdy,
            "sortDirection": "asc",
        }

        scvk_json = _request_json(
            session,
            "GET",
            api_url,
            timeout_seconds=timeout_seconds,
            verify=verify,
            headers=headers,
            params=params,
        )

    if (
        isinstance(scvk_json, list)
        and scvk_json
        and isinstance(scvk_json[0], dict)
        and "measurements" in scvk_json[0]
        and isinstance(scvk_json[0]["measurements"], list)
    ):
        print("Připojeno k SČVK Smart Metering")
        print("Počet záznamů:", max(len(scvk_json[0]["measurements"]) - 1, 0))
        print()
    else:
        raise RuntimeError("Unexpected API response shape from SČVK /api endpoint.")

    return scvk_json















































#
# """ SČVK data
#     Číslo hlavy     Ev. č. OM    Výr. č. vodoměru     Popis
#     IOTW-049672     602003694       017021            DOKTOR voda, Folknářská 1246/21
#     IOTW-049668     602003779       040202            DOKTOR požární voda, Folknářská 1246/21
#     IOTW-049708     681189817       015971            B1 NEWAYS, Benešovská
#     IOTW-049698     681041132       005872            HECHT, Benešovská
#     IOTW-049674     602009738       005354            GROBÁR, Folknářská
#     IOTW-067073     681290535       013445            S1, Folknářská
#     IOTW-066996     602003797       091818            Staré město, Nám. 5.května
#     """
#
#
# paths = {'SCVK_DP': {"oznaceni": "DOKTOR požární voda", "odberne misto": "602003779", "cislo vodomeru": "040202", "cislo hlavy": "IOTW-049668", "denni limit": 20, "stočné": "ne", "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_040202.xlsx"},
#          'SCVK_DV': {"oznaceni": "DOKTOR voda", "odberne misto": "602003694", "cislo vodomeru": "017021", "cislo hlavy": "IOTW-049672", "denni limit": 8, "stočné": "ne", "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_017021.xlsx"},
#          'SCVK_B1': {"oznaceni": "B1 NEWAYS", "odberne misto": "681189817", "cislo vodomeru": "015971", "cislo hlavy": "IOTW-049708", "denni limit": 20, "stočné": "ano", "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_037550.xlsx"},
#          'SCVK_HE': {"oznaceni": "HECHT", "odberne misto": "681041132", "cislo vodomeru": "005872", "cislo hlavy": "IOTW-049698", "denni limit": 10, "stočné": "ano", "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_005872.xlsx"},
#          'SCVK_GR': {"oznaceni": "GROBÁR", "odberne misto": "602009738", "cislo vodomeru": "005354", "cislo hlavy": "IOTW-049674", "denni limit": 8, "stočné": "ne", "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_005354.xlsx"},
#          'SCVK_S1': {"oznaceni": "S1", "odberne misto": "681290535", "cislo vodomeru": "013445", "cislo hlavy": "IOTW-067073", "denni limit": 1, "stočné": "ano"},
#          'SCVK_ST': {"oznaceni": "Staré město", "odberne misto": "602003797", "cislo vodomeru": "091818", "cislo hlavy": "IOTW-066996", "denni limit": 1, "stočné": "ano"}
#          }
#
# pocet_vodomeru = len(paths)
# seznam_vodomeru = list(paths.keys())
#
#
#
# def SCVK_denni_limit(dotazVodomer):
#     return paths[dotazVodomer]['denni limit']
#
#
#
# def get_last_db_date(seriove_cislo):
#     stmt = (
#         select(Vodomer_SCVK_Mereni.date)
#         .where(Vodomer_SCVK_Mereni.seriove_cislo == seriove_cislo)
#         .order_by(Vodomer_SCVK_Mereni.date.desc())
#         .limit(1)
#     )
#
#     with SessionLocalPG() as session:
#         return session.execute(stmt).scalar_one_or_none()
#
#
#
# def SCVK_dotaz(dotazVodomer):
#     """Načtení měření ze SČVK API s robustní validací odpovědí."""
#     scvk_vodomer = paths[dotazVodomer]['cislo hlavy']
#     scvk_cislo_vodomeru = paths[dotazVodomer]['cislo vodomeru']
#     scvk_popis = paths[dotazVodomer]['oznaceni']
#
#     print(f"SČVK {scvk_cislo_vodomeru} - {scvk_popis}")
#
#     odKdy = get_last_db_date(scvk_cislo_vodomeru)
#     if odKdy is None:
#         odKdy = dt.datetime.now() - dt.timedelta(days=7)
#     TsOdKdy = int(odKdy.timestamp() * 1000)
#     print(odKdy)
#
#     ted = dt.datetime.now()
#     TsDoKdy = int(ted.timestamp() * 1000)
#     print(ted.strftime("%Y-%m-%d %H:%M:%S"))
#
#     auth_url = config("URL_SCVK")
#     auth_data = {
#         "username": config('USERNAME_SCVK'),
#         "password": config("PASSWORD_SCVK"),
#     }
#
#     try:
#         auth_response = requests.post(auth_url, json=auth_data, timeout=REQUEST_TIMEOUT)
#         auth_response.raise_for_status()
#         auth_payload = auth_response.json()
#     except requests.RequestException as e:
#         raise RuntimeError(f"SČVK auth request failed: {e}") from e
#     except ValueError as e:
#         raise RuntimeError("SČVK auth response is not valid JSON") from e
#
#     if not isinstance(auth_payload, dict) or not auth_payload:
#         raise RuntimeError(f"Unexpected SČVK auth payload: {auth_payload!r}")
#
#     token_value = next((str(v).strip() for v in auth_payload.values() if v), None)
#     if not token_value:
#         raise RuntimeError(f"Missing token in SČVK auth payload: {auth_payload!r}")
#
#     headers = {"Authorization": f"Bearer {token_value}"}
#     params = {
#         "tsFrom": TsOdKdy,
#         "deviceId": scvk_vodomer,
#         "tsUntil": TsDoKdy,
#         "sortDirection": "asc",
#     }
#
#     api_url = "https://sm.scvoda.cz/api"
#     try:
#         response = requests.get(api_url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
#         response.raise_for_status()
#         print("Připojeno k SČVK Smart Metering")
#         scvk_json = response.json()
#     except requests.RequestException as e:
#         raise RuntimeError(f"SČVK measurement request failed: {e}") from e
#     except ValueError as e:
#         raise RuntimeError("SČVK measurement response is not valid JSON") from e
#
#     if not isinstance(scvk_json, list):
#         raise RuntimeError(
#             f"Unexpected SČVK measurement payload type: {type(scvk_json).__name__}"
#         )
#
#     if not scvk_json:
#         print("Počet záznamů: 0")
#         print()
#         return []
#
#     first_item = scvk_json[0]
#     if not isinstance(first_item, dict) or "measurements" not in first_item:
#         raise RuntimeError(f"Missing 'measurements' in SČVK payload item: {first_item!r}")
#
#     measurements = first_item["measurements"] or []
#     pocet_zaznamu = max(len(measurements) - 1, 0)
#     print(f"Počet záznamů: {pocet_zaznamu}")
#     print()
#
#     return scvk_json
#
#



