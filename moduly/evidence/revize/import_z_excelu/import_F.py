from datetime import timedelta
import math

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.db.connect import ENGINE_PG
from moduly.evidence.revize.database.models import Revize, Revize_zarizeni
from pathlib import Path
import pandas as pd
from icecream import ic


engine = ENGINE_PG

EXCEL_FILE = Path(r"P:\Holding\Správa Majetku\Budovy\F\Revize\Revize F.xlsx")
BUDOVA = "F"
REVIZE_BASE_DIR = Path(r"P:\Holding\Správa Majetku\Budovy\F\Revize")
REVIZE_NAME_SOURCE_COLUMN = "F revize"
REVIZE_NAME_PREFIX = "F - revize"


COLUMN_ALIASES = {
    "termín provedení:": "datum",
    "interval": "interval",
    "Unnamed: 2": "nazev_revize_detail",
    "Unnamed: 6": "jednotka_platnosti",
    "firma": "dodavatel",
    "revize": "soubor",
    "servisní smlouva": "servisni_smlouva",
    "Unnamed: 16": "fid",
}


def load_excel(path):
    df = pd.read_excel(path, header=1)   # první řádek je jen nadpis
    rename_map = {}
    existing_columns = set(df.columns)

    for source, target in COLUMN_ALIASES.items():
        if source not in existing_columns:
            continue
        if target in existing_columns and source != target:
            continue
        rename_map[source] = target

    if rename_map:
        df = df.rename(columns=rename_map)

    return df


def prepare_dataframe(path):
    df = load_excel(path)
    df = clean_rows(df)
    df = add_nazev_revize(df)
    return df


def clean_rows(df):
    df = df.dropna(subset=["datum"]).copy()
    return df


def add_nazev_revize(df):
    df = df.copy()
    source_column = REVIZE_NAME_SOURCE_COLUMN if REVIZE_NAME_SOURCE_COLUMN in df.columns else "nazev_revize"
    # Nazev hlavni skupiny se v Excelu nekdy uvede jen na prvnim radku bloku.
    main_value = df[source_column].ffill() if source_column in df.columns else pd.Series(index=df.index, dtype="object")
    detail_value = df["nazev_revize_detail"] if "nazev_revize_detail" in df.columns else pd.Series(index=df.index, dtype="object")

    def compose_name(main, detail):
        if pd.isna(main):
            return None

        parts = [REVIZE_NAME_PREFIX, str(main).strip()]
        if pd.notna(detail):
            detail_text = str(detail).strip()
            if detail_text:
                parts.append(detail_text)
        return " - ".join(parts)

    df["nazev_revize"] = [
        compose_name(main, detail)
        for main, detail in zip(main_value, detail_value)
    ]

    return df


def parse_fid_list(fid_cell):
    if pd.isna(fid_cell):
        return []

    result = []

    for value in str(fid_cell).split(","):
        value = value.strip()
        if value.isdigit():
            result.append(int(value))

    return result


def compute_platnost(datum, delka):
    if pd.isna(datum):
        return None
    return datum + timedelta(days=365 * float(delka))


def normalize_date(value):
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "date"):
        return value.date()
    return value


def get_row_value(row, column):
    value = row[column]
    if isinstance(value, pd.Series):
        non_empty = value[value.notna()]
        if non_empty.empty:
            return None
        return non_empty.iloc[0]
    if pd.isna(value):
        return None
    return value


def normalize_soubor_path(soubor):
    path = Path(soubor)
    if path.is_absolute():
        return str(path)

    return str(REVIZE_BASE_DIR / path)


def parse_delka_platnosti(row):
    value = float(get_row_value(row, "interval"))
    unit = str(get_row_value(row, "jednotka_platnosti") or "").strip().lower()
    if unit.startswith("měs") or unit.startswith("mes"):
        return value / 12
    return value



def years_to_db_value(years):
    if math.isclose(years, round(years)):
        return int(round(years))

    return years


def build_revize_record(row, budova):
    datum = normalize_date(get_row_value(row, "datum"))
    delka = parse_delka_platnosti(row)

    return {
        "budova": budova,
        "datum": datum,
        "delka_platnosti": years_to_db_value(delka),
        "datum_platnosti": normalize_date(compute_platnost(datum, delka)),
        "typ_zarizeni": get_row_value(row, "typ_zarizeni"),
        "nazev_revize": get_row_value(row, "nazev_revize"),
        "dodavatel": get_row_value(row, "dodavatel"),
        "soubor": normalize_soubor_path(get_row_value(row, "soubor")),
        "servisni_smlouva": get_row_value(row, "servisni_smlouva"),
    }


def build_revize_zarizeni_for_row(row, revize_id):
    typ = get_row_value(row, "typ_zarizeni")
    fid_list = parse_fid_list(get_row_value(row, "fid"))

    if pd.isna(typ) or not typ or not fid_list:
        return []

    return [
        {
            "revize_id": revize_id,
            "typ_zarizeni": typ,
            "zarizeni_id": fid,
        }
        for fid in fid_list
    ]


def find_existing_revize(session, budova, datum, soubor):
    stmt = select(Revize).where(
        Revize.budova == budova,
        Revize.datum == datum,
    )

    if soubor is None:
        stmt = stmt.where(Revize.soubor.is_(None))
    else:
        stmt = stmt.where(Revize.soubor == soubor)

    return session.execute(stmt).scalars().first()


def find_current_revize(session, revize_payload, fid_list):
    # Pokud uz je nektere zarizeni navazane, bereme tuto revizi jako aktualni kandidata.
    if fid_list:
        revize_ids = session.execute(
            select(Revize_zarizeni.revize_id)
            .join(Revize, Revize.id == Revize_zarizeni.revize_id)
            .where(
                Revize.budova == revize_payload["budova"],
                Revize.nazev_revize == revize_payload["nazev_revize"],
                Revize_zarizeni.typ_zarizeni == revize_payload["typ_zarizeni"],
                Revize_zarizeni.zarizeni_id.in_(fid_list),
            )
        ).scalars().all()
        unique_ids = set(revize_ids)
        if len(unique_ids) == 1:
            return session.get(Revize, unique_ids.pop())
        if len(unique_ids) > 1:
            stmt = select(Revize).where(Revize.id.in_(unique_ids)).order_by(Revize.datum.desc(), Revize.id.desc())
            return session.execute(stmt).scalars().first()

    stmt = (
        select(Revize)
        .where(
            Revize.budova == revize_payload["budova"],
            Revize.nazev_revize == revize_payload["nazev_revize"],
            Revize.typ_zarizeni == revize_payload["typ_zarizeni"],
        )
        .order_by(Revize.datum.desc(), Revize.id.desc())
    )
    return session.execute(stmt).scalars().first()


def get_linked_zarizeni_ids(session, revize_id, typ_zarizeni):
    if revize_id is None:
        return set()

    stmt = select(Revize_zarizeni.zarizeni_id).where(
        Revize_zarizeni.revize_id == revize_id,
        Revize_zarizeni.typ_zarizeni == typ_zarizeni,
    )
    return set(session.execute(stmt).scalars().all())


def is_same_revize(current_revize, revize_payload):
    if current_revize is None:
        return False

    comparable_fields = (
        "budova",
        "datum",
        "datum_platnosti",
        "typ_zarizeni",
        "nazev_revize",
        "dodavatel",
        "soubor",
        "servisni_smlouva",
    )

    for field in comparable_fields:
        if getattr(current_revize, field) != revize_payload[field]:
            return False

    return math.isclose(
        float(current_revize.delka_platnosti),
        float(revize_payload["delka_platnosti"]),
    )


def should_skip_row(session, revize_payload, fid_list):
    # Presna shoda podle unikatniho klice Revize znamena, ze nesmime zakladat novy zaznam.
    exact_revize = find_existing_revize(
        session,
        budova=revize_payload["budova"],
        datum=revize_payload["datum"],
        soubor=revize_payload["soubor"],
    )
    if exact_revize is not None:
        exact_fids = get_linked_zarizeni_ids(session, exact_revize.id, revize_payload["typ_zarizeni"])
        if is_same_revize(exact_revize, revize_payload) and exact_fids == set(fid_list):
            return True, exact_revize, False
        return False, exact_revize, False

    # Jinak hledame aktualni revizi podle nazvu, typu a navazanych zarizeni.
    current_revize = find_current_revize(session, revize_payload, fid_list)
    if current_revize is None:
        return False, None, True

    current_fids = get_linked_zarizeni_ids(session, current_revize.id, revize_payload["typ_zarizeni"])
    if not is_same_revize(current_revize, revize_payload):
        return False, current_revize, True

    return current_fids == set(fid_list), current_revize, False


def create_revize(session, revize_payload, stats, is_replacement):
    revize = Revize(**revize_payload)
    session.add(revize)
    session.flush()
    if is_replacement:
        stats["revize_updated"] += 1
    else:
        stats["revize_inserted"] += 1
    return revize


def replace_current_zarizeni_links(session, revize_payload, zarizeni_rows):
    if not zarizeni_rows:
        return 0

    # Historii revizi nechavame v tabulce Revize, ale aktualni vazba zarizeni se ma presunout jen na novou verzi.
    stmt = delete(Revize_zarizeni).where(
        Revize_zarizeni.typ_zarizeni == revize_payload["typ_zarizeni"],
        Revize_zarizeni.zarizeni_id.in_([row["zarizeni_id"] for row in zarizeni_rows]),
        Revize_zarizeni.revize_id.in_(
            select(Revize.id).where(
                Revize.budova == revize_payload["budova"],
                Revize.nazev_revize == revize_payload["nazev_revize"],
                Revize.id != zarizeni_rows[0]["revize_id"],
            )
        ),
    )
    session.execute(stmt)

    stmt = insert(Revize_zarizeni).values(zarizeni_rows)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["revize_id", "typ_zarizeni", "zarizeni_id"]
    )
    session.execute(stmt)
    return len(zarizeni_rows)


def import_excel_to_db(excel_file, budova=BUDOVA, db_engine=engine):
    df = prepare_dataframe(excel_file)
    stats = {
        "rows_in_excel": len(df),
        "revize_processed": 0,
        "revize_inserted": 0,
        "revize_updated": 0,
        "revize_skipped": 0,
        "revize_zarizeni_upserted": 0,
    }

    revize_rows = [build_revize_record(row, budova) for _, row in df.iterrows()]

    with Session(db_engine) as session:
        for (_, row), revize_payload in zip(df.iterrows(), revize_rows):
            fid_list = parse_fid_list(get_row_value(row, "fid"))
            should_skip, current_revize, create_new_revize = should_skip_row(session, revize_payload, fid_list)
            stats["revize_processed"] += 1

            if should_skip:
                stats["revize_skipped"] += 1
                continue

            # Novou Revize vytvarime jen pokud se zmenila samotna revize; zmena vazeb pri stejnem unikatnim klici pouzije existujici zaznam.
            if create_new_revize:
                revize = create_revize(
                    session,
                    revize_payload,
                    stats,
                    is_replacement=current_revize is not None,
                )
            else:
                revize = current_revize

            stats["revize_zarizeni_upserted"] += replace_current_zarizeni_links(
                session,
                revize_payload,
                build_revize_zarizeni_for_row(row, revize.id),
            )

        session.commit()

    return stats


if __name__ == "__main__":
    stats = import_excel_to_db(EXCEL_FILE, budova=BUDOVA, db_engine=ENGINE_PG)
    ic(stats)


# ic(prepare_dataframe(EXCEL_FILE))
