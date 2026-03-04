import datetime as dt
import requests
from decouple import config
from sqlalchemy import select
from moduly.mereni.vodomery.database.models import Vodomer_SCVK_Mereni
from core.db.connect import SessionLocalPG

REQUEST_TIMEOUT = 15

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


paths = {'SCVK_DP': {"oznaceni": "DOKTOR požární voda", "odberne misto": "602003779", "cislo vodomeru": "040202", "cislo hlavy": "IOTW-049668", "denni limit": 20, "stočné": "ne", "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_040202.xlsx"},
         'SCVK_DV': {"oznaceni": "DOKTOR voda", "odberne misto": "602003694", "cislo vodomeru": "017021", "cislo hlavy": "IOTW-049672", "denni limit": 8, "stočné": "ne", "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_017021.xlsx"},
         'SCVK_B1': {"oznaceni": "B1 NEWAYS", "odberne misto": "681189817", "cislo vodomeru": "015971", "cislo hlavy": "IOTW-049708", "denni limit": 20, "stočné": "ano", "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_037550.xlsx"},
         'SCVK_HE': {"oznaceni": "HECHT", "odberne misto": "681041132", "cislo vodomeru": "005872", "cislo hlavy": "IOTW-049698", "denni limit": 10, "stočné": "ano", "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_005872.xlsx"},
         'SCVK_GR': {"oznaceni": "GROBÁR", "odberne misto": "602009738", "cislo vodomeru": "005354", "cislo hlavy": "IOTW-049674", "denni limit": 8, "stočné": "ne", "path": r"P:\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\SČVK stavy\smart_odečty_pro_meřidlo_005354.xlsx"},
         'SCVK_S1': {"oznaceni": "S1", "odberne misto": "681290535", "cislo vodomeru": "013445", "cislo hlavy": "IOTW-067073", "denni limit": 1, "stočné": "ano"},
         'SCVK_ST': {"oznaceni": "Staré město", "odberne misto": "602003797", "cislo vodomeru": "091818", "cislo hlavy": "IOTW-066996", "denni limit": 1, "stočné": "ano"}
         }

pocet_vodomeru = len(paths)
seznam_vodomeru = list(paths.keys())



def SCVK_denni_limit(dotazVodomer):
    return paths[dotazVodomer]['denni limit']



def get_last_db_date(seriove_cislo):
    stmt = (
        select(Vodomer_SCVK_Mereni.date)
        .where(Vodomer_SCVK_Mereni.seriove_cislo == seriove_cislo)
        .order_by(Vodomer_SCVK_Mereni.date.desc())
        .limit(1)
    )

    with SessionLocalPG() as session:
        return session.execute(stmt).scalar_one_or_none()



def SCVK_dotaz(dotazVodomer):
    """Načtení měření ze SČVK API s robustní validací odpovědí."""
    scvk_vodomer = paths[dotazVodomer]['cislo hlavy']
    scvk_cislo_vodomeru = paths[dotazVodomer]['cislo vodomeru']
    scvk_popis = paths[dotazVodomer]['oznaceni']

    print(f"SČVK {scvk_cislo_vodomeru} - {scvk_popis}")

    odKdy = get_last_db_date(scvk_cislo_vodomeru)
    if odKdy is None:
        odKdy = dt.datetime.now() - dt.timedelta(days=7)
    TsOdKdy = int(odKdy.timestamp() * 1000)
    print(odKdy)

    ted = dt.datetime.now()
    TsDoKdy = int(ted.timestamp() * 1000)
    print(ted.strftime("%Y-%m-%d %H:%M:%S"))

    auth_url = config("URL_SCVK")
    auth_data = {
        "username": config('USERNAME_SCVK'),
        "password": config("PASSWORD_SCVK"),
    }

    try:
        auth_response = requests.post(auth_url, json=auth_data, timeout=REQUEST_TIMEOUT)
        auth_response.raise_for_status()
        auth_payload = auth_response.json()
    except requests.RequestException as e:
        raise RuntimeError(f"SČVK auth request failed: {e}") from e
    except ValueError as e:
        raise RuntimeError("SČVK auth response is not valid JSON") from e

    if not isinstance(auth_payload, dict) or not auth_payload:
        raise RuntimeError(f"Unexpected SČVK auth payload: {auth_payload!r}")

    token_value = next((str(v).strip() for v in auth_payload.values() if v), None)
    if not token_value:
        raise RuntimeError(f"Missing token in SČVK auth payload: {auth_payload!r}")

    headers = {"Authorization": f"Bearer {token_value}"}
    params = {
        "tsFrom": TsOdKdy,
        "deviceId": scvk_vodomer,
        "tsUntil": TsDoKdy,
        "sortDirection": "asc",
    }

    api_url = "https://sm.scvoda.cz/api"
    try:
        response = requests.get(api_url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        print("Připojeno k SČVK Smart Metering")
        scvk_json = response.json()
    except requests.RequestException as e:
        raise RuntimeError(f"SČVK measurement request failed: {e}") from e
    except ValueError as e:
        raise RuntimeError("SČVK measurement response is not valid JSON") from e

    if not isinstance(scvk_json, list):
        raise RuntimeError(
            f"Unexpected SČVK measurement payload type: {type(scvk_json).__name__}"
        )

    if not scvk_json:
        print("Počet záznamů: 0")
        print()
        return []

    first_item = scvk_json[0]
    if not isinstance(first_item, dict) or "measurements" not in first_item:
        raise RuntimeError(f"Missing 'measurements' in SČVK payload item: {first_item!r}")

    measurements = first_item["measurements"] or []
    pocet_zaznamu = max(len(measurements) - 1, 0)
    print(f"Počet záznamů: {pocet_zaznamu}")
    print()

    return scvk_json


# Původní verze funkce ponechána zakomentovaná dle požadavku:
# def SCVK_dotaz(dotazVodomer):
#     """ přiravit hodnoty pro další použití """
#     scvk_vodomer = paths[dotazVodomer]['cislo hlavy'] # GET dotaz
#     scvk_cislo_vodomeru = paths[dotazVodomer]['cislo vodomeru'] # get_last_db_date
#     scvk_popis = paths[dotazVodomer]['oznaceni'] # popis
#
#     print(f"SČVK {scvk_cislo_vodomeru} - {scvk_popis}")
#
#     """ SČVK komunikace"""
#     """ vyřešení času (od - do) dotazu na SČVK """
#     """ od posledního záznamu v db """
#     odKdy = get_last_db_date(scvk_cislo_vodomeru)
#     if odKdy is None:
#         # Fallback for first run when DB has no history for this meter.
#         odKdy = dt.datetime.now() - dt.timedelta(days=7)
#     TsOdKdy = int(odKdy.timestamp() * 1000)
#     print(odKdy)
#
#     """ za poslední týden """
#     # days_to_subtract = 5
#     # predTydnem = dt.datetime.today() - dt.timedelta(days=days_to_subtract)
#     # TsOdKdy = int(predTydnem.timestamp() * 1000)
#     # print(predTydnem)
#
#     """ zadat datum """
#     # zadane_datum = '2025.09.26-7:59:59'
#     # date_object = dt.datetime.strptime(zadane_datum, '%Y.%m.%d-%H:%M:%S')
#
#     """ do teď  """
#     ted = dt.datetime.now()
#     TsDoKdy = int(ted.timestamp() * 1000)
#     # TsDoKdy = int(dt.datetime.now().timestamp() * 1000)
#     ted_str = ted.strftime("%Y-%m-%d %H:%M:%S")
#     print(ted_str)
#
#     """ získat token pro přihlášení POST dotazem """
#     url = config("URL_SCVK")
#     data = {
#         "username": config('USERNAME_SCVK'),
#         "password": config("PASSWORD_SCVK"),
#     }
#
#     response = requests.post(url, json=data)
#     # response.raise_for_status()
#
#     ScvkToken = None
#
#     for key, value in response.json().items():
#         ScvkToken = "Bearer " + value
#         break
#
#     """ připravit data na GET dotaz """
#     headers = {"Authorization": ScvkToken}
#
#     params = {
#         "tsFrom": TsOdKdy,
#         "deviceId": scvk_vodomer,
#         "tsUntil": TsDoKdy,
#         "sortDirection": "asc"
#     }
#
#     """ GET dotaz měření """
#     url = "https://sm.scvoda.cz/api"
#     response = requests.get(url, params=params, headers=headers)
#     if response.status_code == 200:
#         print("Připojeno k SČVK Smart Metering")
#     else:
#         print(f"Error: {response.status_code}")
#     #     # response.raise_for_status()
#
#     SCVK_Json = response.json()
#     pocet_zaznamu = len(SCVK_Json[0]['measurements'])-1
#     print(f"Počet záznamů: {pocet_zaznamu}")
#     print()
#
#     return SCVK_Json



