from __future__ import annotations

import html
from datetime import datetime

from decouple import config

from app.channels.email import send_email_outlook
from moduly.mereni.vodomery.reporting._email_config import (
    filter_placeholder_recipients,
    load_report_recipients,
    sanitize_sender_alias,
)


def send_vodomery_model_rebuild_report(selection_result: dict[str, object]) -> dict[str, object]:
    recipients = filter_placeholder_recipients(
        _load_recipients(),
        context_label="send_vodomery_model_rebuild_report",
    )
    if not recipients:
        return {
            "selection_run_id": selection_result["selection_run_id"],
            "active_model_version": selection_result["active_model_version"],
            "active_model_name": selection_result["active_model_name"],
            "recipient_count": 0,
            "candidate_count": len(selection_result.get("candidates", [])),
            "skipped": True,
            "skip_reason": "no_sendable_recipients",
        }
    subject = (
        "Vodomer model rebuild | "
        f"aktivni model {selection_result['active_model_name']} (v{selection_result['active_model_version']})"
    )
    body = _build_email_body(selection_result)

    for recipient in recipients:
        send_email_outlook(
            email_receiver=recipient,
            subject=subject,
            body=body,
            sender_alias=sanitize_sender_alias(
                config("O_EMAIL_UPOZORNENI", default=None),
                context_label="VODOMERY_MODEL_REBUILD_REPORT_SENDER_ALIAS",
            ),
            is_html=True,
        )

    return {
        "selection_run_id": selection_result["selection_run_id"],
        "active_model_version": selection_result["active_model_version"],
        "active_model_name": selection_result["active_model_name"],
        "recipient_count": len(recipients),
        "candidate_count": len(selection_result.get("candidates", [])),
    }


def _load_recipients() -> list[str]:
    return list(
        load_report_recipients(
            "VODOMERY_MODEL_REBUILD_REPORT_RECIPIENTS",
        )
    )


def _build_email_body(selection_result: dict[str, object]) -> str:
    windows = selection_result["windows"]
    candidate_rows = selection_result.get("candidates", [])
    active_version = selection_result["active_model_version"]
    active_name = selection_result["active_model_name"]
    previous_version = selection_result.get("previous_active_model_version")
    previous_name = selection_result.get("previous_active_model_name")
    selection_run_id = selection_result["selection_run_id"]

    header_html = (
        "<p style='margin:0 0 16px;'>"
        "Tydenni rebuild profilu vodomeru byl dokonceny. "
        f"Do produkce byl nasazen <strong>{html.escape(str(active_name))}</strong> "
        f"(v{html.escape(str(active_version))})."
        "</p>"
    )
    if previous_version != active_version:
        header_html += (
            "<p style='margin:0 0 16px;'>"
            f"Predchozi aktivni model: <strong>{html.escape(str(previous_name))}</strong> "
            f"(v{html.escape(str(previous_version))})."
            "</p>"
        )

    period_rows = "".join(
        (
            "<tr>"
            f"<td style='padding:6px 10px;border:1px solid #d0d7de;background:#f6f8fa;'><strong>{html.escape(label)}</strong></td>"
            f"<td style='padding:6px 10px;border:1px solid #d0d7de;'>{html.escape(_format_datetime(value))}</td>"
            "</tr>"
        )
        for label, value in (
            ("Selection run", selection_run_id),
            ("Train start", windows["train_start"]),
            ("Train end", windows["train_end"]),
            ("Validation start", windows["validation_start"]),
            ("Validation end", windows["validation_end"]),
            ("Deploy start", windows["deploy_start"]),
            ("Deploy end", windows["deploy_end"]),
        )
    )

    candidate_table_rows = "".join(
        _build_candidate_row(candidate_row)
        for candidate_row in candidate_rows
    )

    return (
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328;'>"
        "<h2 style='margin:0 0 12px;'>Tydenni validace modelu vodomeru</h2>"
        f"{header_html}"
        "<table style='border-collapse:collapse;font-size:14px;margin-bottom:20px;'>"
        f"{period_rows}"
        "</table>"
        "<table style='border-collapse:collapse;font-size:14px;min-width:920px;'>"
        "<tr>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Model</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Validace</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Matched</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Coverage</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>MAE</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>RMSE</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Bias</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Profily</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Selected devices</th>"
        "</tr>"
        f"{candidate_table_rows}"
        "</table>"
        "</body></html>"
    )


def _build_candidate_row(candidate_row: dict[str, object]) -> str:
    selected = bool(candidate_row.get("selected"))
    background = "#e6f4ea" if selected else "#ffffff"
    model_label = f"{candidate_row['model_name']} (v{candidate_row['model_version']})"
    if selected:
        model_label = f"{model_label} - aktivni"

    return (
        "<tr>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};'>{html.escape(model_label)}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{int(candidate_row['validation_total_count'])}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{int(candidate_row['matched_validation_count'])}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_percentage(candidate_row.get('coverage'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_metric(candidate_row.get('mae'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_metric(candidate_row.get('rmse'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_metric(candidate_row.get('bias'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{int(candidate_row['profile_count'])}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_optional_int(candidate_row.get('selected_device_count'))}</td>"
        "</tr>"
    )


def _format_datetime(value: object) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _format_percentage(value: object) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.1f} %"


def _format_metric(value: object) -> str:
    if value is None:
        return "-"
    return f"{float(value):.4f}"


def _format_optional_int(value: object) -> str:
    if value is None:
        return "-"
    return str(int(value))
