import datetime
import time

from decouple import config

from moduly.mereni.vodomery.SCVK.SCVK_data_z_dotazu import SCVK_dotaz, seznam_vodomeru
from core.db.connect import SessionLocalPG

from moduly.mereni.vodomery.database.models import Vodomer_SCVK_Zarizeni, Vodomer_SCVK_Alarm, Vodomer_SCVK_Mereni




def save_to_database(SCVK_Json):
    """Save SCVK data to PostgreSQL database"""

    if isinstance(SCVK_Json, list):
        if not SCVK_Json:
            print("No data received")
            return
        data_item = SCVK_Json[0]
    else:
        data_item = SCVK_Json

    with SessionLocalPG() as session:
        # --- DEVICE ---
        device = (
            session.query(Vodomer_SCVK_Zarizeni)
            .filter_by(seriove_cislo=data_item['vdmId'])
            .first()
        )

        if not device:
            device = Vodomer_SCVK_Zarizeni(
                seriove_cislo=data_item['vdmId'],
                odberne_misto=data_item['omId'],
                MBUS=data_item['deviceId'],
                mm_id=data_item['mmId'],
                instalovano=datetime.datetime.fromtimestamp(
                    data_item['tsInstalled'] / 1000
                ),
            )
            session.add(device)

        # --- ALARMS ---
        for alarm_data in data_item.get('alarms', []):
            exists = (
                session.query(Vodomer_SCVK_Alarm)
                .filter_by(recid=alarm_data['id'])
                .first()
            )

            if not exists:
                alarm = Vodomer_SCVK_Alarm(
                    recid=alarm_data['id'],
                    odberne_misto=data_item['omId'],
                    seriove_cislo=data_item['vdmId'],
                    active=alarm_data['active'],
                    alarm_start=datetime.datetime.fromtimestamp(
                        alarm_data['tsStart'] / 1000
                    ),
                    alarm_stop=(
                        datetime.datetime.fromtimestamp(
                            alarm_data['tsStop'] / 1000
                        )
                        if alarm_data['tsStop'] != 0
                        else None
                    ),
                    type=alarm_data['type'],
                )
                session.add(alarm)

        # --- MEASUREMENTS ---
        for measure_data in data_item.get('measurements', []):
            ts = datetime.datetime.fromtimestamp(measure_data['ts'] / 1000)

            exists = (
                session.query(Vodomer_SCVK_Mereni)
                .filter_by(
                    seriove_cislo=data_item['vdmId'],
                    date=ts,
                )
                .first()
            )

            if not exists:
                measurement = Vodomer_SCVK_Mereni(
                    odberne_misto=data_item['omId'],
                    seriove_cislo=data_item['vdmId'],
                    objem=round(measure_data['measurement'], 3),
                    platne=measure_data['valid'],
                    date=ts,
                    temp=measure_data['temp'],
                    identifikace=device.identifikace,
                )
                session.add(measurement)

        session.commit()





def SCVK_save_to_database_all():
    """Save SCVK data for all vodoměry"""
    delay_between_meters = config(
        "SCVK_BETWEEN_METERS_SLEEP_SECONDS", default=1.5, cast=float
    )

    for index, vodomer in enumerate(seznam_vodomeru):
        try:
            save_to_database(SCVK_dotaz(vodomer))
        except Exception as exc:
            print(f"Chyba pro vodoměr {vodomer}: {exc}")
        if index < len(seznam_vodomeru) - 1 and delay_between_meters > 0:
            time.sleep(delay_between_meters)

































# def save_to_database(SCVK_Json):
#     """Save SCVK data to PostgreSQL database"""
#
#     if isinstance(SCVK_Json, list):
#         if not SCVK_Json:
#             print("No data received")
#             return
#         data_item = SCVK_Json[0]
#     else:
#         data_item = SCVK_Json
#
#     with SessionLocalPG() as session:
#         # --- DEVICE ---
#         device = (
#             session.query(Vodomer_SCVK_Zarizeni)
#             .filter_by(seriove_cislo=data_item['vdmId'])
#             .first()
#         )
#
#         if not device:
#             device = Vodomer_SCVK_Zarizeni(
#                 seriove_cislo=data_item['vdmId'],
#                 odberne_misto=data_item['omId'],
#                 MBUS=data_item['deviceId'],
#                 mm_id=data_item['mmId'],
#                 instalovano=datetime.datetime.fromtimestamp(
#                     data_item['tsInstalled'] / 1000
#                 ),
#             )
#             session.add(device)
#
#         # --- ALARMS ---
#         for alarm_data in data_item.get('alarms', []):
#             exists = (
#                 session.query(Vodomer_SCVK_Alarm)
#                 .filter_by(recid=alarm_data['id'])
#                 .first()
#             )
#
#             if not exists:
#                 alarm = Vodomer_SCVK_Alarm(
#                     recid=alarm_data['id'],
#                     odberne_misto=data_item['omId'],
#                     seriove_cislo=data_item['vdmId'],
#                     active=alarm_data['active'],
#                     alarm_start=datetime.datetime.fromtimestamp(
#                         alarm_data['tsStart'] / 1000
#                     ),
#                     alarm_stop=(
#                         datetime.datetime.fromtimestamp(
#                             alarm_data['tsStop'] / 1000
#                         )
#                         if alarm_data['tsStop'] != 0
#                         else None
#                     ),
#                     type=alarm_data['type'],
#                 )
#                 session.add(alarm)
#
#         # --- MEASUREMENTS ---
#         for measure_data in data_item.get('measurements', []):
#             ts = datetime.datetime.fromtimestamp(measure_data['ts'] / 1000)
#
#             exists = (
#                 session.query(Vodomer_SCVK_Mereni)
#                 .filter_by(
#                     seriove_cislo=data_item['vdmId'],
#                     date=ts,
#                 )
#                 .first()
#             )
#
#             if not exists:
#                 measurement = Vodomer_SCVK_Mereni(
#                     odberne_misto=data_item['omId'],
#                     seriove_cislo=data_item['vdmId'],
#                     objem=round(measure_data['measurement'], 3),
#                     platne=measure_data['valid'],
#                     date=ts,
#                     temp=measure_data['temp'],
#                     identifikace=str(device.identifikace),
#                 )
#                 session.add(measurement)
#
#         session.commit()
#
#
#
#
#
#
# def SCVK_save_to_database_all():
#     """Save SCVK data for all vodoměry"""
#     for vodomer in seznam_vodomeru:
#         save_to_database(SCVK_dotaz(vodomer))
