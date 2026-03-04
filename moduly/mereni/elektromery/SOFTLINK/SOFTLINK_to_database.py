from core.db.connect import SessionLocalMS
from moduly.mereni.elektromery.database.models import Elektromer_areal_Zarizeni, Elektromer_areal_Mereni
from collections import defaultdict
from datetime import datetime, timezone
from moduly.mereni.elektromery.SOFTLINK.SOFTLINK_data_z_dotazu import SOFTLINK_dotaz


def SOFTLINK_to_database_mereni(api_json):

    if not api_json or "data" not in api_json:
        return

    data_list = api_json["data"]

    with SessionLocalMS() as session:

        # 🔹 mapování zařízení – identifikace = odběrné místo

        zarizeni_map = {}

        rows = session.query(
            Elektromer_areal_Zarizeni.softlink_id,
            Elektromer_areal_Zarizeni.identifikace,
            Elektromer_areal_Zarizeni.seriove_cislo,
        ).all()

        for softlink_id, identifikace, seriove_cislo in rows:
            zarizeni_map[softlink_id] = {
                "identifikace": identifikace,
                "seriove_cislo": seriove_cislo,
            }

        grouped = defaultdict(lambda: {
            "vt": None,
            "nt": None,
            "total": None,
            "vt_var_id": None,
            "nt_var_id": None,
            "total_var_id": None,
        })

        # 1️⃣ seskupení měření
        for item in data_list:

            if item.get("var_type") != 1:
                continue

            pot_id = item.get("pot_id")
            if pot_id not in (1, 2, 4):
                continue

            ts_raw = item.get("var_lasttime")
            if ts_raw is None:
                continue

            ts = datetime.fromtimestamp(ts_raw / 1000, tz=timezone.utc)
            key = (item["me_id"], ts)

            if pot_id == 1:        # VT
                grouped[key]["vt"] = item["var_lastvar"]
                grouped[key]["vt_var_id"] = item["var_id"]

            elif pot_id == 2:      # NT
                grouped[key]["nt"] = item["var_lastvar"]
                grouped[key]["nt_var_id"] = item["var_id"]

            elif pot_id == 4:      # TOTAL
                grouped[key]["total"] = item["var_lastvar"]
                grouped[key]["total_var_id"] = item["var_id"]


        # 2️⃣ uložení do DB
        for (me_id, date_ts), vals in grouped.items():

            zarizeni = zarizeni_map.get(me_id)
            if not zarizeni:
                continue

            # 🔹 identifikace = odběrné místo z tabulky zařízení
            identifikace = zarizeni["identifikace"]
            seriove_cislo = zarizeni["seriove_cislo"]

            # kontrola duplicity
            exists = session.query(Elektromer_areal_Mereni).filter(
                Elektromer_areal_Mereni.softlink_id == me_id,
                Elektromer_areal_Mereni.date == date_ts,
            ).first()

            if exists:
                continue

            session.add(
                Elektromer_areal_Mereni(
                    identifikace=identifikace,
                    seriove_cislo=seriove_cislo,

                    vt=vals["vt"] or vals["total"],
                    nt=vals["nt"],
                    total=vals["total"],

                    vt_var_id=vals["vt_var_id"] or vals["total_var_id"],
                    nt_var_id=vals["nt_var_id"],
                    total_var_id=vals["total_var_id"],

                    date=date_ts,
                    softlink_id=me_id,
                )
            )

        session.commit()
