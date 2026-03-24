import logging
import math
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from moduly.evidence.revize.database.models import Revize, Revize_zarizeni
from moduly.evidence.revize.import_z_excelu.extractors import extract_records


LOGGER = logging.getLogger(__name__)


def build_revize_zarizeni_for_record(record, revize_id):
    typ = record["typ_zarizeni"]
    fid_list = record["fid_list"]

    if not typ or not fid_list:
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
        LOGGER.info(
            "Building %s created replacement revize_id=%s for '%s' (%s)",
            revize_payload["budova"],
            revize.id,
            revize_payload["nazev_revize"],
            revize_payload["soubor"],
        )
    else:
        stats["revize_inserted"] += 1
        LOGGER.info(
            "Building %s created revize_id=%s for '%s' (%s)",
            revize_payload["budova"],
            revize.id,
            revize_payload["nazev_revize"],
            revize_payload["soubor"],
        )
    return revize


def replace_current_zarizeni_links(session, revize_payload, zarizeni_rows):
    if not zarizeni_rows:
        LOGGER.info(
            "Building %s has no device links for '%s'",
            revize_payload["budova"],
            revize_payload["nazev_revize"],
        )
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
    LOGGER.info(
        "Building %s linked %s devices to revize_id=%s for '%s'",
        revize_payload["budova"],
        len(zarizeni_rows),
        zarizeni_rows[0]["revize_id"],
        revize_payload["nazev_revize"],
    )
    return len(zarizeni_rows)


def import_excel_to_db(config, db_engine):
    records, warnings = extract_records(config)
    for warning in warnings:
        LOGGER.warning(warning)

    stats = {
        "rows_in_excel": len(records),
        "revize_processed": 0,
        "revize_inserted": 0,
        "revize_updated": 0,
        "revize_skipped": 0,
        "revize_zarizeni_upserted": 0,
        "warnings": warnings,
    }

    with Session(db_engine) as session:
        for record in records:
            revize_payload = {key: value for key, value in record.items() if key != "fid_list"}
            fid_list = record["fid_list"]
            should_skip, current_revize, create_new_revize = should_skip_row(session, revize_payload, fid_list)
            stats["revize_processed"] += 1

            if should_skip:
                stats["revize_skipped"] += 1
                LOGGER.info(
                    "Building %s skipped unchanged revize '%s' (%s)",
                    revize_payload["budova"],
                    revize_payload["nazev_revize"],
                    revize_payload["soubor"],
                )
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
                LOGGER.info(
                    "Building %s reused existing revize_id=%s for '%s' and refreshed links",
                    revize_payload["budova"],
                    revize.id,
                    revize_payload["nazev_revize"],
                )

            stats["revize_zarizeni_upserted"] += replace_current_zarizeni_links(
                session,
                revize_payload,
                build_revize_zarizeni_for_record(record, revize.id),
            )

        session.commit()

    LOGGER.info("Import %s finished: %s", config.budova, stats)
    return stats
