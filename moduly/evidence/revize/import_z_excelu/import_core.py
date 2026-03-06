import openpyxl
from sqlalchemy.orm import Session
from datetime import timedelta
from moduly.evidence.revize.database.models import Revize, Revize_zarizeni


def import_revize(engine, excel_file, budova, row_mapping, column_mapping):

    wb = openpyxl.load_workbook(excel_file, data_only=True)
    ws = wb.active

    with Session(engine) as session:

        for row in ws.iter_rows():

            druh = row[0].value
            if druh not in row_mapping:
                continue

            typ_zarizeni = row_mapping[druh]

            datum = row[3].value
            delka = row[5].value
            dodavatel = row[7].value
            soubor = row[8].value
            servisni = row[9].value
            fid_list = row[16].value

            if not datum:
                continue

            datum_platnosti = None
            if datum and delka:
                datum_platnosti = datum + timedelta(days=delka*30)

            revize = Revize(
                budova=budova,
                datum=datum,
                delka_platnosti=delka,
                datum_platnosti=datum_platnosti,
                dodavatel=dodavatel,
                servisni_smlouva=servisni,
                soubor=soubor
            )

            session.add(revize)
            session.flush()

            if fid_list:

                fid_list = [
                    int(fid.strip())
                    for fid in str(fid_list).split(",")
                    if fid.strip().isdigit()
                ]

                for fid in fid_list:

                    rz = Revize_zarizeni(
                        revize_id=revize.id,
                        typ_zarizeni=typ_zarizeni,
                        zarizeni_id=fid
                    )

                    session.add(rz)

        session.commit()