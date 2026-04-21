from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from core.db.connect import ENGINE_PG


logger = logging.getLogger(__name__)


def drop_legacy_identifikace_fk(table_name: str) -> None:
    inspector = inspect(ENGINE_PG)
    if table_name not in inspector.get_table_names(schema="monitoring"):
        return
    for foreign_key in inspector.get_foreign_keys(table_name, schema="monitoring"):
        name = foreign_key.get("name")
        constrained_columns = tuple(foreign_key.get("constrained_columns") or ())
        referred_schema = foreign_key.get("referred_schema")
        referred_table = foreign_key.get("referred_table")
        if (
            name
            and constrained_columns == ("identifikace",)
            and referred_schema == "evidence"
            and referred_table == "vodoměry"
        ):
            escaped_name = str(name).replace('"', '""')
            with ENGINE_PG.begin() as conn:
                conn.execute(
                    text(
                        f'ALTER TABLE monitoring."{table_name}" '
                        f'DROP CONSTRAINT IF EXISTS "{escaped_name}"'
                    )
                )
            logger.info(
                'Dropped legacy foreign key "%s" from monitoring."%s"',
                name,
                table_name,
            )
