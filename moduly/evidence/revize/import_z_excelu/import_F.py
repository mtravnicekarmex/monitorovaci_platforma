from core.db.connect import ENGINE_PG
from moduly.evidence.revize.import_z_excelu.import_core import import_revize
from pathlib import Path
import pandas as pd
from icecream import ic


# Set options for pandas display
pd.set_option('display.max_rows', 1000)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
pd.reset_option('display.float_format')


engine = ENGINE_PG

EXCEL_FILE = Path(r"P:\Holding\Správa Majetku\Budovy\F\Revize\Revize F.xlsx")
BUDOVA = "F"


# Mapování sloupců v Excelu
REVIZE_MAPPING_COLUMNS = {
    "Unnamed: 3": "datum",
    "Unnamed: 5": "delka_platnosti",
    "Unnamed: 7": "dodavatel",
    "Unnamed: 8": "soubor",
    "Unnamed: 9": "servisni_smlouva",
    "Q": "fid_list"
}

# Mapování názvu řádku → typ tabulky zařízení
TYP_MAP = {
    "rozdody plynu": "PLYNOVÁ ZAŘÍZENÍ",
    "plynové kotle": "PLYNOVÁ ZAŘÍZENÍ",
    "plynové zářiče": "PLYNOVÁ ZAŘÍZENÍ",
    "spalinové cesty kotle": "SPALINOVÉ CESTY",
    "spalinové cesty zářiče": "SPALINOVÉ CESTY",
    "hasící přístroje": "HASÍCÍ PŘÍSTROJE",
    "požární hydranty a suchovody": "HYDRANTY",
    "hromosvody": "HROMOSVODY",
    "nouzové osvětlení": "ELEKTROREVIZE",
    "požární uzávěry a rolety": "POŽÁRNÍ UZÁVĚRY A ROLETY",
    "požární ucpávky": "POŽÁRNÍ UCPÁVKY",
    "požární klapky": "POŽÁRNÍ KLAPKY",
    "požární dveře": "POŽÁRNÍ DVEŘE",
    "požární schodiště": "POŽÁRNÍ SCHODIŠTĚ",
    "TOTAL STOP":  "ELEKTROREVIZE",
    "EPS": "ELEKTROREVIZE",

}

def load_excel(path):

    df = pd.read_excel(path, header=1)   # první řádek je jen nadpis

    return df


def clean_rows(df):

    df = df.dropna(subset=["termín provedení:"])

    return df


def map_typ_zarizeni(df):

    df["typ_zarizeni"] = df["F revize"].map(TYP_MAP)

    return df


def parse_fid_list(fid_cell):

    if pd.isna(fid_cell):
        return []

    return [int(x.strip()) for x in str(fid_cell).split(",")]


def compute_platnost(datum, delka):

    return datum + timedelta(days=365 * int(delka))


def build_revize(df, budova):

    revize = []

    for _, row in df.iterrows():

        datum = row["termín provedení:"]
        interval = row["interval"]

        delka = int(interval) if interval else 1

        revize.append({

            "budova": budova,
            "datum": datum,
            "delka_platnosti": delka,
            "datum_platnosti": compute_platnost(datum, delka),
            "dodavatel": row["firma"],
            "soubor": row["revize"],
            "servisni_smlouva": row["servisní smlouva"]

        })

    return revize


def build_revize_zarizeni(df, revize_ids):

    result = []

    for i, row in df.iterrows():

        typ = row["typ_zarizeni"]
        fid_list = parse_fid_list(row["fid list"])

        for fid in fid_list:

            result.append({

                "revize_id": revize_ids[i],
                "typ_zarizeni": typ,
                "zarizeni_id": fid

            })

    return result




# session.bulk_insert_mappings(Revize, revize_data)
# session.commit()
#
# session.bulk_insert_mappings(Revize_zarizeni, zarizeni_data)
# session.commit()



df = load_excel(EXCEL_FILE)
ic(df)
df = clean_rows(df)
ic(df)
df = map_typ_zarizeni(df)
ic(df)