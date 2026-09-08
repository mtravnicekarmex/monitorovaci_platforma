from __future__ import annotations

import json

from sqlalchemy import inspect, text

from core.db.connect import ENGINE_PG
from moduly.apps.dashboard.database.models import Base
from moduly.apps.web_search.database.db_init import ensure_web_search_tables
from moduly.mereni.vodomery.database.expected_zero import ensure_expected_zero_table
from moduly.mereni.vodomery.database.alerting import ensure_vodomery_alerting_tables
from moduly.mereni.vodomery.database.outlier_reviews import ensure_vodomery_outlier_review_table
from moduly.mereni.vodomery.alerting.outlier_notifications import ensure_vodomery_outlier_email_delivery_table
from moduly.mereni.plynomery.database.alerting import ensure_plynomery_alerting_tables
from moduly.mereni.plynomery.database.expected_zero import ensure_expected_zero_table as ensure_plynomery_expected_zero_table
from moduly.mereni.plynomery.database.outlier_reviews import ensure_plynomery_outlier_review_table
from moduly.mereni.plynomery.alerting.outlier_notifications import ensure_plynomery_outlier_email_delivery_table
from moduly.mereni.kalorimetry.database.outlier_reviews import ensure_kalorimetry_outlier_review_table
from moduly.mereni.elektromery.database.elektromery_db_vse import ensure_elektromery_vse_table
from moduly.apps.smartfuelpass.database.db_init import ensure_smartfuelpass_tables
from services.api.services.map_layers import ensure_default_map_layers


def ensure_streamlit_user_columns() -> None:
    inspector = inspect(ENGINE_PG)
    try:
        columns = {column["name"] for column in inspector.get_columns("Streamlit_Users", schema="dashboard")}
    except Exception:
        return

    alter_statements: list[str] = []
    if "dostupne_sekce" not in columns:
        alter_statements.append('ALTER TABLE dashboard."Streamlit_Users" ADD COLUMN dostupne_sekce TEXT')
    if "dostupne_stranky" not in columns:
        alter_statements.append('ALTER TABLE dashboard."Streamlit_Users" ADD COLUMN dostupne_stranky TEXT')
    if "token_version" not in columns:
        alter_statements.append(
            'ALTER TABLE dashboard."Streamlit_Users" ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0'
        )

    if not alter_statements:
        return

    with ENGINE_PG.begin() as conn:
        for statement in alter_statements:
            conn.execute(text(statement))


def _append_map_layer_json_list_columns(conn, *, layer_id: str, field_name: str, columns: tuple[str, ...]) -> None:
    row = conn.execute(
        text(f'SELECT {field_name} FROM dashboard."Map_Layers" WHERE layer_id = :layer_id'),
        {"layer_id": layer_id},
    ).first()
    if row is None:
        return
    try:
        current = json.loads(str(row[0] or "[]"))
    except json.JSONDecodeError:
        current = []
    if not isinstance(current, list):
        current = []

    cleaned = [str(item).strip() for item in current if str(item).strip()]
    changed = False
    for column in columns:
        if column not in cleaned:
            cleaned.append(column)
            changed = True
    if changed:
        conn.execute(
            text(f'UPDATE dashboard."Map_Layers" SET {field_name} = :value WHERE layer_id = :layer_id'),
            {
                "layer_id": layer_id,
                "value": json.dumps(cleaned, ensure_ascii=True),
            },
        )


def ensure_map_layer_columns() -> None:
    inspector = inspect(ENGINE_PG)
    try:
        columns = {column["name"] for column in inspector.get_columns("Map_Layers", schema="dashboard")}
    except Exception:
        return

    valid_map_contexts = ("evidence", "revize", "pronajem", "shared")
    quoted_contexts = ", ".join(f"'{context}'" for context in valid_map_contexts)
    alter_statements: list[str] = []
    if "map_context" not in columns:
        alter_statements.append(
            'ALTER TABLE dashboard."Map_Layers" '
            "ADD COLUMN map_context VARCHAR(50) NOT NULL DEFAULT 'evidence'"
        )
    if "show_photo" not in columns:
        alter_statements.append(
            'ALTER TABLE dashboard."Map_Layers" '
            "ADD COLUMN show_photo BOOLEAN NOT NULL DEFAULT FALSE"
        )
    if "map_label_columns" not in columns:
        alter_statements.append(
            'ALTER TABLE dashboard."Map_Layers" '
            "ADD COLUMN map_label_columns TEXT NOT NULL DEFAULT '[]'"
        )
    if "map_labels_default_visible" not in columns:
        alter_statements.append(
            'ALTER TABLE dashboard."Map_Layers" '
            "ADD COLUMN map_labels_default_visible BOOLEAN NOT NULL DEFAULT TRUE"
        )
    if "sync_mistnosti_filters" not in columns:
        alter_statements.append(
            'ALTER TABLE dashboard."Map_Layers" '
            "ADD COLUMN sync_mistnosti_filters BOOLEAN NOT NULL DEFAULT FALSE"
        )
    if "property_labels" not in columns:
        alter_statements.append(
            'ALTER TABLE dashboard."Map_Layers" '
            "ADD COLUMN property_labels TEXT NOT NULL DEFAULT '{}'"
        )
    if "document_columns" not in columns:
        alter_statements.append(
            'ALTER TABLE dashboard."Map_Layers" '
            "ADD COLUMN document_columns TEXT NOT NULL DEFAULT '{}'"
        )

    with ENGINE_PG.begin() as conn:
        for statement in alter_statements:
            conn.execute(text(statement))
        conn.execute(
            text(
                'UPDATE dashboard."Map_Layers" '
                "SET map_context = 'evidence' "
                f"WHERE map_context IS NULL OR btrim(map_context) = '' OR map_context NOT IN ({quoted_contexts})"
            )
        )
        conn.execute(text('ALTER TABLE dashboard."Map_Layers" DROP CONSTRAINT IF EXISTS map_layers_map_context_check'))
        conn.execute(
            text(
                'ALTER TABLE dashboard."Map_Layers" '
                f"ADD CONSTRAINT map_layers_map_context_check CHECK (map_context IN ({quoted_contexts}))"
            )
        )
        if "show_photo" not in columns:
            conn.execute(
                text(
                    'UPDATE dashboard."Map_Layers" '
                    "SET show_photo = TRUE WHERE layer_id = 'vodomery'"
                )
            )
        if "sync_mistnosti_filters" not in columns:
            conn.execute(
                text(
                    'UPDATE dashboard."Map_Layers" '
                    "SET sync_mistnosti_filters = TRUE "
                    "WHERE layer_kind = 'device' "
                    "OR lower(layer_id) IN ('vodovodni_potrubi', 'vodovodni_uzly', 'vzt')"
                )
            )
        if "map_label_columns" not in columns:
            conn.execute(
                text(
                    'UPDATE dashboard."Map_Layers" '
                    "SET map_label_columns = '[\"mistnost\"]' WHERE layer_id = 'mistnosti'"
                )
            )
        for field_name in ("filter_columns", "property_columns"):
            _append_map_layer_json_list_columns(
                conn,
                layer_id="revize_terminy_zarizeni",
                field_name=field_name,
                columns=("budova", "patro"),
            )


def ensure_dashboard_tables() -> None:
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS dashboard"))

    Base.metadata.create_all(bind=ENGINE_PG)
    ensure_streamlit_user_columns()
    ensure_map_layer_columns()
    ensure_default_map_layers()
    ensure_web_search_tables()
    ensure_expected_zero_table()
    ensure_plynomery_expected_zero_table()
    ensure_vodomery_alerting_tables()
    ensure_vodomery_outlier_review_table()
    ensure_vodomery_outlier_email_delivery_table()
    ensure_plynomery_alerting_tables()
    ensure_plynomery_outlier_review_table()
    ensure_plynomery_outlier_email_delivery_table()
    ensure_kalorimetry_outlier_review_table()
    ensure_elektromery_vse_table()
    ensure_smartfuelpass_tables()


if __name__ == "__main__":
    ensure_dashboard_tables()
