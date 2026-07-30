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


def send_plynomery_model_rebuild_report(selection_result: dict[str, object]) -> dict[str, object]:
    recipients = filter_placeholder_recipients(
        _load_recipients(),
        context_label="send_plynomery_model_rebuild_report",
    )
    if not recipients:
        return {
            "selection_run_id": selection_result.get("selection_run_id"),
            "active_model_version": selection_result["active_model_version"],
            "active_model_name": selection_result["active_model_name"],
            "recipient_count": 0,
            "candidate_count": len(selection_result.get("candidates", [])),
            "dry_run_fallback_count": int(
                selection_result.get("dry_run_fallback_count") or 0
            ),
            "dry_run_unavailable_count": int(
                selection_result.get("dry_run_unavailable_count") or 0
            ),
            "skipped": True,
            "skip_reason": "no_sendable_recipients",
        }

    subject = (
        "Plynomer model rebuild | "
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
                context_label="PLYNOMERY_MODEL_REBUILD_REPORT_SENDER_ALIAS",
            ),
            is_html=True,
        )

    return {
        "selection_run_id": selection_result.get("selection_run_id"),
        "active_model_version": selection_result["active_model_version"],
        "active_model_name": selection_result["active_model_name"],
        "recipient_count": len(recipients),
        "candidate_count": len(selection_result.get("candidates", [])),
        "dry_run_fallback_count": int(
            selection_result.get("dry_run_fallback_count") or 0
        ),
        "dry_run_unavailable_count": int(
            selection_result.get("dry_run_unavailable_count") or 0
        ),
    }


def _load_recipients() -> list[str]:
    return list(
        load_report_recipients(
            "PLYNOMERY_MODEL_REBUILD_REPORT_RECIPIENTS",
            fallback_env_keys=("VODOMERY_MODEL_REBUILD_REPORT_RECIPIENTS",),
        )
    )


def _build_email_body(selection_result: dict[str, object]) -> str:
    windows = selection_result["windows"]
    candidate_rows = selection_result.get("candidates", [])
    active_version = selection_result["active_model_version"]
    active_name = selection_result["active_model_name"]
    previous_version = selection_result.get("previous_active_model_version")
    previous_name = selection_result.get("previous_active_model_name")
    selection_run_id = selection_result.get("selection_run_id")

    header_html = (
        "<p style='margin:0 0 16px;'>"
        "Tydenni rebuild profilu plynomeru byl dokonceny. "
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
    dry_run_summary_html = _build_dry_run_summary_html(selection_result)

    return (
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328;'>"
        "<h2 style='margin:0 0 12px;'>Tydenni validace modelu plynomeru</h2>"
        f"{header_html}"
        "<table style='border-collapse:collapse;font-size:14px;margin-bottom:20px;'>"
        f"{period_rows}"
        "</table>"
        f"{dry_run_summary_html}"
        "<table style='border-collapse:collapse;font-size:14px;min-width:920px;'>"
        "<tr>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Model</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Validace</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Matched</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Coverage</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>MAE</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>RMSE</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Bias</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Rolling coverage</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Rolling WAPE</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Profily</th>"
        "</tr>"
        f"{candidate_table_rows}"
        "</table>"
        f"{_build_metric_explanation_html()}"
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
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_percentage(candidate_row.get('rolling_coverage'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_percentage(candidate_row.get('rolling_wape'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{int(candidate_row['profile_count'])}</td>"
        "</tr>"
    )


def _build_dry_run_summary_html(selection_result: dict[str, object]) -> str:
    selection_mode = str(
        selection_result.get("selection_mode") or "dry_run"
    ).strip().lower()
    selection_label = "Aktivni" if selection_mode == "active" else "Dry-run"
    decisions = [
        row
        for row in selection_result.get("dry_run_selected_models", [])
        if isinstance(row, dict)
    ]
    if not decisions:
        return ""

    winner_counts = selection_result.get("dry_run_winner_counts", {})
    winner_text = ", ".join(
        f"v{html.escape(str(version))}: {int(count)}"
        for version, count in sorted(
            winner_counts.items(),
            key=lambda item: int(item[0]),
        )
    ) or "-"
    fallback_counts: dict[str, int] = {}
    for decision in decisions:
        reason = str(decision.get("fallback_reason") or "none")
        if reason != "none":
            fallback_counts[reason] = fallback_counts.get(reason, 0) + 1
    fallback_text = ", ".join(
        f"{html.escape(reason)}: {count}"
        for reason, count in sorted(fallback_counts.items())
    ) or "zadne"

    worst = sorted(
        (
            decision
            for decision in decisions
            if isinstance(decision.get("metrics"), dict)
            and decision["metrics"].get("wape") is not None
            and decision.get("fallback_reason") != "insufficient_history"
        ),
        key=lambda decision: float(decision["metrics"]["wape"]),
        reverse=True,
    )[:10]
    worst_rows = "".join(
        (
            "<tr>"
            f"<td style='padding:6px 8px;border:1px solid #d0d7de;'>{html.escape(str(row.get('identifier') or '-'))}</td>"
            f"<td style='padding:6px 8px;border:1px solid #d0d7de;text-align:right;'>v{int(row['selected_model_version'])}</td>"
            f"<td style='padding:6px 8px;border:1px solid #d0d7de;text-align:right;'>{_format_percentage(row['metrics'].get('coverage'))}</td>"
            f"<td style='padding:6px 8px;border:1px solid #d0d7de;text-align:right;'>{_format_percentage(row['metrics'].get('wape'))}</td>"
            f"<td style='padding:6px 8px;border:1px solid #d0d7de;'>{html.escape(str(row.get('fallback_reason') or 'none'))}</td>"
            "</tr>"
        )
        for row in worst
    )
    worst_table = ""
    if worst_rows:
        worst_table = (
            "<p style='margin:14px 0 6px;'><strong>Nejhorsi identifikatory podle rolling WAPE:</strong></p>"
            "<table style='border-collapse:collapse;font-size:13px;margin-bottom:20px;'>"
            "<tr><th style='padding:6px 8px;border:1px solid #d0d7de;'>Identifikator</th>"
            "<th style='padding:6px 8px;border:1px solid #d0d7de;'>Model</th>"
            "<th style='padding:6px 8px;border:1px solid #d0d7de;'>Coverage</th>"
            "<th style='padding:6px 8px;border:1px solid #d0d7de;'>WAPE</th>"
            "<th style='padding:6px 8px;border:1px solid #d0d7de;'>Fallback</th></tr>"
            f"{worst_rows}</table>"
        )

    return (
        "<div style='font-size:14px;margin-bottom:18px;'>"
        f"<p style='margin:0 0 6px;'><strong>{selection_label} "
        "per-identifier vyber:</strong></p>"
        f"<p style='margin:0 0 4px;'>Rozdeleni vitezu: {winner_text}</p>"
        f"<p style='margin:0 0 4px;'>Fallbacky: {fallback_text}</p>"
        f"<p style='margin:0 0 4px;'>Predikce nedostupna "
        f"(nedostatecna historie): "
        f"{int(selection_result.get('dry_run_unavailable_count') or 0)}</p>"
        f"<p style='margin:0;'>Deployable dvojice/profily: "
        f"{int(selection_result.get('deployable_profile_pair_count') or 0)} / "
        f"{int(selection_result.get('deployable_profile_count') or 0)}</p>"
        f"{worst_table}"
        "</div>"
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


def _build_metric_explanation_html() -> str:
    return (
        "<div style='font-size:13px;line-height:1.45;margin-top:14px;color:#57606a;max-width:920px;'>"
        "<p style='margin:0 0 6px;'><strong>Vysvetleni metrik:</strong></p>"
        "<p style='margin:0 0 4px;'><strong>MAE</strong> je prumerna absolutni chyba predikce. "
        "Nizsi hodnota znamena presnejsi model.</p>"
        "<p style='margin:0 0 4px;'><strong>RMSE</strong> je odmocnina prumerne kvadraticke chyby. "
        "Vice zvyraznuje velke odchylky, proto je citlivejsi na spicky.</p>"
        "<p style='margin:0;'><strong>Bias</strong> je prumerna podepsana chyba "
        "(skutecna spotreba minus predikce). Kladna hodnota znamena, ze model spotrebu spis podhodnocuje; "
        "zaporna hodnota znamena, ze ji spis nadhodnocuje.</p>"
        "</div>"
    )
