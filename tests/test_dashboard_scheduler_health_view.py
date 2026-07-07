from moduly.apps.dashboard.scheduler_health_view import (
    manual_run_confirmation_text,
    manual_run_impact_label,
    manual_run_requires_confirmation,
)


def test_manual_run_requires_confirmation_for_scheduled_job():
    row = {
        "id": "quarter_hour_job",
        "label": "Ctvrthodinovy job",
        "description": "Import a scoring vodomeru.",
        "is_scheduled": True,
    }

    assert manual_run_requires_confirmation(row) is True
    assert manual_run_impact_label(row) == "potvrzeni vyzadovano"


def test_manual_run_requires_confirmation_for_email_report_step():
    row = {
        "id": "send_monthly_vodomery_consumption_report",
        "label": "Mesicni report spotreby vodomeru",
        "description": "Odeslani mesicniho reportu spotreby vodomeru.",
        "is_scheduled": False,
    }

    assert manual_run_requires_confirmation(row) is True
    assert "send_monthly_vodomery_consumption_report" in manual_run_confirmation_text(row)


def test_manual_run_requires_confirmation_for_database_sync_step():
    row = {
        "id": "sync_charge_sessions_to_db",
        "label": "Zapis SmartFuelPass relaci do databaze",
        "description": "Synchronizace relaci do PostgreSQL.",
        "is_scheduled": False,
    }

    assert manual_run_requires_confirmation(row) is True


def test_manual_run_allows_low_impact_database_check():
    row = {
        "id": "check_database_availability",
        "label": "Kontrola dostupnosti databazi",
        "description": "Overi dostupnost PostgreSQL a MSSQL.",
        "is_scheduled": False,
    }

    assert manual_run_requires_confirmation(row) is False
    assert manual_run_impact_label(row) == "bezna kontrola"
