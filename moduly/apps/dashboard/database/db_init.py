from __future__ import annotations

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
from moduly.mereni.elektromery.database.hlavni_xlsx_import import ensure_elektromery_ote_table
from moduly.mereni.elektromery.database.elektromery_db_vse import ensure_elektromery_vse_table
from moduly.apps.smartfuelpass.database.db_init import ensure_smartfuelpass_tables


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


def ensure_dashboard_tables() -> None:
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS dashboard"))

    Base.metadata.create_all(bind=ENGINE_PG)
    ensure_streamlit_user_columns()
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
    ensure_elektromery_ote_table()
    ensure_elektromery_vse_table()
    ensure_smartfuelpass_tables()


if __name__ == "__main__":
    ensure_dashboard_tables()
