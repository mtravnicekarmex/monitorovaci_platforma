from __future__ import annotations

from collections.abc import Mapping


LOW_IMPACT_MANUAL_JOB_IDS = {
    "check_database_availability",
    "get_runtime_model_version",
    "get_plynomery_runtime_model_version",
}

HIGH_IMPACT_JOB_ID_PREFIXES = (
    "send_",
    "process_",
    "score_",
    "detect_",
    "rebuild_",
    "sync_",
)

HIGH_IMPACT_JOB_ID_PARTS = (
    "_import",
    "_job",
    "_report",
    "save_to_database",
    "meteo_sync",
)

HIGH_IMPACT_TEXT_PARTS = (
    "email",
    "odeslani",
    "report",
    "import",
    "synchroniz",
    "zapis",
    "databaze",
)


def _as_text(value: object) -> str:
    return str(value or "").strip()


def manual_run_requires_confirmation(row: Mapping[str, object]) -> bool:
    job_id = _as_text(row.get("id")).lower()
    if job_id in LOW_IMPACT_MANUAL_JOB_IDS:
        return False
    if bool(row.get("is_scheduled")):
        return True
    if any(job_id.startswith(prefix) for prefix in HIGH_IMPACT_JOB_ID_PREFIXES):
        return True
    if any(part in job_id for part in HIGH_IMPACT_JOB_ID_PARTS):
        return True

    searchable_text = " ".join(
        [
            _as_text(row.get("label")),
            _as_text(row.get("description")),
        ]
    ).lower()
    return any(part in searchable_text for part in HIGH_IMPACT_TEXT_PARTS)


def manual_run_impact_label(row: Mapping[str, object]) -> str:
    if manual_run_requires_confirmation(row):
        return "potvrzeni vyzadovano"
    return "bezna kontrola"


def manual_run_confirmation_text(row: Mapping[str, object]) -> str:
    job_id = _as_text(row.get("id")) or "vybrany cil"
    return (
        f"Vybrany cil `{job_id}` muze zapisovat data, odeslat email/report "
        "nebo spustit navazne importy. Spoustej ho jen pri jasnem provoznim duvodu."
    )
