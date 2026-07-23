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
            "device_candidate_count": len(selection_result.get("device_candidates", [])),
            "selected_model_snapshot_count": int(
                selection_result.get("selected_model_snapshot_count") or 0
            ),
            "prediction_profile_snapshot_count": int(
                selection_result.get("prediction_profile_snapshot_count") or 0
            ),
            "prediction_profile_snapshot_missing_pair_count": int(
                selection_result.get("prediction_profile_snapshot_missing_pair_count") or 0
            ),
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
        "device_candidate_count": len(selection_result.get("device_candidates", [])),
        "selected_model_snapshot_count": int(
            selection_result.get("selected_model_snapshot_count") or 0
        ),
        "prediction_profile_snapshot_count": int(
            selection_result.get("prediction_profile_snapshot_count") or 0
        ),
        "prediction_profile_snapshot_missing_pair_count": int(
            selection_result.get("prediction_profile_snapshot_missing_pair_count") or 0
        ),
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
    device_candidate_rows = selection_result.get("device_candidates", [])
    selected_model_snapshot_rows = selection_result.get("selected_model_snapshots", [])
    active_version = selection_result["active_model_version"]
    active_name = selection_result["active_model_name"]
    previous_version = selection_result.get("previous_active_model_version")
    previous_name = selection_result.get("previous_active_model_name")
    selection_run_id = selection_result["selection_run_id"]
    forecast_period = selection_result.get("forecast_period")
    snapshot_mode = selection_result.get("selected_model_snapshot_mode")
    snapshot_count = selection_result.get("selected_model_snapshot_count")
    profile_snapshot_source = selection_result.get("prediction_profile_snapshot_source")
    profile_snapshot_count = selection_result.get("prediction_profile_snapshot_count")
    profile_snapshot_pair_count = selection_result.get("prediction_profile_snapshot_pair_count")
    profile_snapshot_missing_pair_count = selection_result.get(
        "prediction_profile_snapshot_missing_pair_count",
    )
    rebuild_duration = selection_result.get("rebuild_duration_seconds")

    header_html = (
        "<p style='margin:0 0 16px;'>"
        "Tydenni rebuild profilu vodomeru byl dokonceny. "
        f"Globalne aktivni model pro zapis skore a fallback je <strong>{html.escape(str(active_name))}</strong> "
        f"(v{html.escape(str(active_version))}). Per-misto selection muze pro konkretni odberna mista pouzit presnejsi profil."
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
            ("Rebuild duration", _format_duration(rebuild_duration)),
            ("Train start", windows["train_start"]),
            ("Train end", windows["train_end"]),
            ("Validation start", windows["validation_start"]),
            ("Validation end", windows["validation_end"]),
            ("Deploy start", windows["deploy_start"]),
            ("Deploy end", windows["deploy_end"]),
            ("Profile snapshot source", _format_optional_text(profile_snapshot_source)),
            ("Profile snapshot rows", _format_optional_int(profile_snapshot_count)),
            ("Profile snapshot pairs", _format_optional_int(profile_snapshot_pair_count)),
            (
                "Missing profile snapshot pairs",
                _format_optional_int(profile_snapshot_missing_pair_count),
            ),
        )
    )

    candidate_table_rows = "".join(
        _build_candidate_row(candidate_row)
        for candidate_row in candidate_rows
    )
    selected_model_snapshot_summary_html = _build_selected_model_snapshot_summary_html(
        selected_model_snapshot_rows,
        device_candidate_rows,
        forecast_period=forecast_period,
        selection_mode=snapshot_mode,
        persisted_count=snapshot_count,
    )

    return (
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328;'>"
        "<h2 style='margin:0 0 12px;'>Tydenni validace modelu vodomeru</h2>"
        f"{header_html}"
        "<table style='border-collapse:collapse;font-size:14px;margin-bottom:20px;'>"
        f"{period_rows}"
        "</table>"
        "<table style='border-collapse:collapse;font-size:14px;min-width:1240px;'>"
        "<tr>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Model</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Eligibility</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Validace</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Matched</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Coverage</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>MAE</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>RMSE</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Bias</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Rolling folds</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Rolling coverage</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Rolling WAPE</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Rolling MAE</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Rolling RMSE</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Rolling bias</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Profily</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Selected devices</th>"
        "</tr>"
        f"{candidate_table_rows}"
        "</table>"
        f"{_build_candidate_table_explanation_html()}"
        f"{_build_device_backtest_summary_html(device_candidate_rows)}"
        f"{selected_model_snapshot_summary_html}"
        f"{_build_metric_explanation_html()}"
        "</body></html>"
    )


def _build_candidate_row(candidate_row: dict[str, object]) -> str:
    selected = bool(candidate_row.get("selected"))
    selection_enabled = bool(candidate_row.get("selection_enabled", True))
    background = "#e6f4ea" if selected else "#ffffff"
    model_label = f"{candidate_row['model_name']} (v{candidate_row['model_version']})"
    if selected:
        model_label = f"{model_label} - aktivni"
    elif not selection_enabled:
        model_label = f"{model_label} - measured only"

    return (
        "<tr>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};'>{html.escape(model_label)}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};'>{html.escape(_format_eligibility(selection_enabled))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{int(candidate_row['validation_total_count'])}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{int(candidate_row['matched_validation_count'])}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_percentage(candidate_row.get('coverage'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_metric(candidate_row.get('mae'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_metric(candidate_row.get('rmse'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_metric(candidate_row.get('bias'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_optional_int(candidate_row.get('rolling_backtest_fold_count'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_percentage(candidate_row.get('rolling_coverage'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_percentage(candidate_row.get('rolling_wape'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_metric(candidate_row.get('rolling_mae'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_metric(candidate_row.get('rolling_rmse'))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:{background};text-align:right;'>{_format_metric(candidate_row.get('rolling_bias'))}</td>"
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


def _format_optional_text(value: object) -> str:
    if value is None:
        return "-"
    normalized = str(value).strip()
    return normalized or "-"


def _format_duration(value: object) -> str:
    if value is None:
        return "-"
    total_seconds = max(0.0, float(value))
    if total_seconds < 60:
        return f"{total_seconds:.1f} s"

    minutes, seconds = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{int(minutes)} min {seconds:.1f} s"

    hours, minutes = divmod(int(minutes), 60)
    return f"{hours} h {minutes} min {seconds:.1f} s"


def _format_eligibility(selection_enabled: bool) -> str:
    return "eligible" if selection_enabled else "measured only"


def _format_identifier_list(identifiers: list[str]) -> str:
    normalized = sorted(
        {str(identifier).strip() for identifier in identifiers if str(identifier).strip()}
    )
    return ", ".join(normalized) if normalized else "-"


def _build_explanation_block_html(
    title: str,
    items: tuple[tuple[str, str], ...],
) -> str:
    item_rows = "".join(
        (
            "<li style='margin:0 0 4px;'>"
            f"<strong>{html.escape(label)}</strong>: {html.escape(description)}"
            "</li>"
        )
        for label, description in items
    )
    return (
        "<div style='font-size:13px;line-height:1.45;margin:10px 0 18px;color:#57606a;max-width:1120px;'>"
        f"<p style='margin:0 0 6px;'><strong>{html.escape(title)}:</strong></p>"
        "<ul style='margin:0 0 0 18px;padding:0;'>"
        f"{item_rows}"
        "</ul>"
        "</div>"
    )


def _build_candidate_table_explanation_html() -> str:
    items = (
        ("Model", "Kandidatni predikcni model. Radek oznaceny 'aktivni' je globalni model pro zapis skore, porovnani a fallback; per-misto selection muze pro konkretni mista pouzit jiny eligible profil."),
        ("Eligibility", "'eligible' znamena, ze model muze byt automaticky vybran. 'measured only' znamena, ze model pouze merime v reportu a zatim se nesmi nasadit."),
        ("Validace", "Pocet validacnich zaznamu v poslednim validacnim okne."),
        ("Matched", "Pocet validacnich zaznamu, pro ktere mel model dostupny profil a slo spocitat chybu."),
        ("Coverage", "Podil Matched / Validace. Vyssi hodnota znamena lepsi pokryti dat."),
        ("MAE", "Prumerna absolutni chyba v poslednim validacnim okne. Nizsi hodnota je lepsi."),
        ("RMSE", "Odmocnina prumerne kvadraticke chyby. Vice zvyraznuje velke odchylky."),
        ("Bias", "Prumerna podepsana chyba: skutecnost minus predikce. Kladna hodnota znamena spis podhodnoceni spotreby, zaporna nadhodnoceni."),
        ("Rolling folds", "Pocet tydennich historickych oken pouzitych pro stabilnejsi backtest."),
        ("Rolling coverage", "Coverage agregovana pres rolling backtest okna."),
        ("Rolling WAPE", "Vazena absolutni procentni chyba: soucet absolutnich chyb / soucet skutecne spotreby. Hlavni porovnavaci metrika, nizsi je lepsi."),
        ("Rolling MAE / RMSE / bias", "Stejne metriky jako MAE, RMSE a Bias, ale agregovane pres rolling backtest okna."),
        ("Profily", "Pocet predikcnich profilu ulozenych pro dany model."),
        ("Selected devices", "Pouze u Modelu 2: pocet odbernych mist, pro ktera si adaptivni model interni logikou vybral jednu ze svych strategii. Neni to per-misto produkcni vyber modelu."),
    )
    return _build_explanation_block_html(
        "Popis sloupcu tabulky Model",
        items,
    )


def _build_device_backtest_summary_html(
    device_candidate_rows: object,
    *,
    detail_row_limit: int | None = None,
) -> str:
    if not isinstance(device_candidate_rows, list) or not device_candidate_rows:
        return ""

    best_rows = [
        row
        for row in device_candidate_rows
        if isinstance(row, dict) and row.get("best_for_identifier")
    ]
    if not best_rows:
        return ""

    winner_identifiers: dict[str, list[str]] = {}
    for row in best_rows:
        model_label = _format_device_model_label(row)
        winner_identifiers.setdefault(model_label, []).append(
            str(row.get("identifikace", "-"))
        )

    winner_rows = "".join(
        (
            "<tr>"
            f"<td style='padding:6px 10px;border:1px solid #d0d7de;'>{html.escape(model_label)}</td>"
            f"<td style='padding:6px 10px;border:1px solid #d0d7de;text-align:right;'>{len(identifiers)}</td>"
            f"<td style='padding:6px 10px;border:1px solid #d0d7de;'>{html.escape(_format_identifier_list(identifiers))}</td>"
            "</tr>"
        )
        for model_label, identifiers in sorted(
            winner_identifiers.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
    )

    detail_rows = sorted(
        best_rows,
        key=lambda row: (
            str(row.get("identifikace", "")),
        ),
    )
    if detail_row_limit is not None:
        detail_rows = detail_rows[:detail_row_limit]
    detail_table_rows = "".join(
        _build_device_backtest_row(row)
        for row in detail_rows
    )

    return (
        "<h3 style='margin:22px 0 8px;'>Per-odberne misto rolling backtest</h3>"
        "<p style='margin:0 0 10px;color:#57606a;font-size:13px;'>"
        "Tato cast ukazuje historicky rolling backtest po odbernych mistech. "
        "Tyto metriky jsou zdrojem pro per-misto vyber modelu pro dalsi forecast obdobi."
        "</p>"
        "<table style='border-collapse:collapse;font-size:14px;margin-bottom:14px;'>"
        "<tr>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Nejlepsi model</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Pocet mist</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Odberna mista</th>"
        "</tr>"
        f"{winner_rows}"
        "</table>"
        "<p style='margin:0 0 8px;color:#57606a;font-size:13px;'>"
        f"Detail nize obsahuje vsechna odberna mista s dostupnymi rolling metrikami ({len(detail_rows)} radku)."
        "</p>"
        "<table style='border-collapse:collapse;font-size:14px;min-width:880px;margin-bottom:10px;'>"
        "<tr>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Odberne misto</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Nejlepsi model</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Rolling WAPE</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Rolling MAE</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Coverage</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Matched</th>"
        "</tr>"
        f"{detail_table_rows}"
        "</table>"
        f"{_build_device_backtest_explanation_html()}"
    )


def _build_device_backtest_row(row: dict[str, object]) -> str:
    model_label = f"{row.get('model_name', 'Model')} (v{row.get('model_version', '-')})"
    if not bool(row.get("selection_enabled", True)):
        model_label = f"{model_label} - measured only"

    return (
        "<tr>"
        f"<td style='padding:7px 10px;border:1px solid #d0d7de;'>{html.escape(str(row.get('identifikace', '-')))}</td>"
        f"<td style='padding:7px 10px;border:1px solid #d0d7de;'>{html.escape(model_label)}</td>"
        f"<td style='padding:7px 10px;border:1px solid #d0d7de;text-align:right;'>{_format_percentage(row.get('rolling_wape'))}</td>"
        f"<td style='padding:7px 10px;border:1px solid #d0d7de;text-align:right;'>{_format_metric(row.get('rolling_mae'))}</td>"
        f"<td style='padding:7px 10px;border:1px solid #d0d7de;text-align:right;'>{_format_percentage(row.get('rolling_coverage'))}</td>"
        f"<td style='padding:7px 10px;border:1px solid #d0d7de;text-align:right;'>{_format_optional_int(row.get('rolling_matched_validation_count'))}</td>"
        "</tr>"
    )


def _build_device_backtest_explanation_html() -> str:
    items = (
        ("Nejlepsi model", "Model s nejmensi historickou chybou pro dane odberne misto podle rolling metrik. Nemusi byt aktualne produkcne nasazeny."),
        ("Pocet mist", "Kolik odbernych mist ma dany model jako nejpresnejsi v rolling backtestu."),
        ("Odberna mista", "Seznam identifikaci odbernych mist, pro ktera je dany model nejpresnejsi."),
        ("Rolling WAPE", "Hlavni porovnavaci chyba pro dane misto pres rolling backtest. Nizsi hodnota je lepsi."),
        ("Rolling MAE", "Prumerna absolutni chyba pro dane misto pres rolling backtest."),
        ("Coverage", "Podil validacnich zaznamu, pro ktere existovala predikce."),
        ("Matched", "Pocet validacnich zaznamu, ktere sly srovnat s predikci."),
        ("Measured only", "Model se meri a muze byt nejpresnejsi v historii, ale zatim neni povoleny pro automaticky vyber."),
    )
    return _build_explanation_block_html(
        "Popis tabulek per-odberne misto",
        items,
    )


def _build_selected_model_snapshot_summary_html(
    selected_model_snapshot_rows: object,
    device_candidate_rows: object,
    *,
    forecast_period: object,
    selection_mode: object,
    persisted_count: object,
    worst_row_limit: int = 12,
) -> str:
    if (
        not isinstance(selected_model_snapshot_rows, list)
        or not selected_model_snapshot_rows
    ):
        return ""

    snapshot_rows = [
        row
        for row in selected_model_snapshot_rows
        if isinstance(row, dict)
    ]
    if not snapshot_rows:
        return ""

    total_count = len(snapshot_rows)
    fallback_rows = [
        row
        for row in snapshot_rows
        if _snapshot_uses_fallback(row)
    ]
    different_from_global_count = sum(
        1
        for row in snapshot_rows
        if _snapshot_differs_from_global(row)
    )
    same_as_global_count = total_count - different_from_global_count

    summary_rows = [
        ("Rezim vyberu", "-" if selection_mode is None else str(selection_mode)),
        ("Obdobi, pro ktere by vyber platil", _format_forecast_period(forecast_period)),
        ("Odberna mista s navrhem", str(total_count)),
        ("Ulozena rozhodnuti", _format_optional_int(persisted_count)),
        ("Navrh stejny jako globalni model", str(same_as_global_count)),
        ("Navrh jiny nez globalni model", str(different_from_global_count)),
        ("Fallback na globalni model", str(len(fallback_rows))),
    ]
    summary_table_rows = "".join(
        (
            "<tr>"
            f"<td style='padding:6px 10px;border:1px solid #d0d7de;background:#f6f8fa;'><strong>{html.escape(label)}</strong></td>"
            f"<td style='padding:6px 10px;border:1px solid #d0d7de;text-align:right;'>{html.escape(value)}</td>"
            "</tr>"
        )
        for label, value in summary_rows
    )

    selected_counts = _count_snapshot_selected_models(snapshot_rows)
    selected_model_rows = _build_count_rows(selected_counts)

    fallback_counts = _count_snapshot_fallback_reasons(fallback_rows)
    fallback_html = (
        "<p style='margin:0 0 14px;color:#57606a;font-size:13px;'>"
        "Zadny fallback nebyl potreba. Pro vsechna mista sel vybrat eligible model z per-misto metrik."
        "</p>"
        if not fallback_counts
        else (
            "<p style='margin:0 0 8px;color:#57606a;font-size:13px;'>"
            "Fallback znamena, ze pro odberne misto neslo bezpecne pouzit per-misto vyber, "
            "takze navrh zustal u globalne aktivniho modelu."
            "</p>"
            "<table style='border-collapse:collapse;font-size:14px;margin-bottom:14px;'>"
            "<tr>"
            "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Fallback duvod</th>"
            "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Pocet mist</th>"
            "</tr>"
            f"{_build_count_rows(fallback_counts)}"
            "</table>"
        )
    )

    measured_only_counts = _count_measured_only_would_win(device_candidate_rows)
    measured_only_html = (
        "<p style='margin:0 0 14px;color:#57606a;font-size:13px;'>"
        "Zadny measured-only kandidat nebyl nejpresnejsi pro zadne odberne misto."
        "</p>"
        if not measured_only_counts
        else (
            "<p style='margin:0 0 8px;color:#57606a;font-size:13px;'>"
            "Measured-only kandidat muze v historickem backtestu vyhrat, ale neni povoleny pro navrzeny "
            "per-misto vyber. Tyto radky slouzi jen jako signal pro dalsi ladeni modelu."
            "</p>"
            "<table style='border-collapse:collapse;font-size:14px;margin-bottom:14px;'>"
            "<tr>"
            "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Measured-only would-win kandidat</th>"
            "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Pocet mist</th>"
            "</tr>"
            f"{_build_count_rows(measured_only_counts)}"
            "</table>"
        )
    )

    worst_rows = _select_worst_selected_snapshot_rows(
        snapshot_rows,
        limit=worst_row_limit,
    )
    worst_html = (
        "<p style='margin:0 0 14px;color:#57606a;font-size:13px;'>"
        "Zadny navrzeny eligible vyber nema dostupnou rolling WAPE metriku."
        "</p>"
        if not worst_rows
        else (
            "<p style='margin:0 0 8px;color:#57606a;font-size:13px;'>"
            "Tato kontrolni tabulka ukazuje nejhorsi navrzene eligible vybery podle rolling WAPE. "
            "Nejde o vsechna odberna mista, ale o mista, kde je chyba navrzeneho modelu nejvyssi."
            "</p>"
            "<table style='border-collapse:collapse;font-size:14px;min-width:900px;margin-bottom:16px;'>"
            "<tr>"
            "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Odberne misto</th>"
            "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Vybrany model</th>"
            "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Rolling WAPE</th>"
            "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Rolling MAE</th>"
            "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Coverage</th>"
            "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Matched</th>"
            "</tr>"
            f"{''.join(_build_selected_snapshot_worst_row(row) for row in worst_rows)}"
            "</table>"
        )
    )

    active_selection_mode = str(selection_mode).strip().lower() == "active"
    section_title = (
        "Aktivni vyber modelu pro dalsi obdobi"
        if active_selection_mode
        else "Dry-run navrh vyberu modelu pro dalsi obdobi"
    )
    section_description = (
        "Tato cast ukazuje ulozeny per-misto vyber modelu pro produkcni scoring v dalsim forecast obdobi. "
        "Globalne aktivni model zustava bezpecny fallback pro mista bez pouzitelneho per-misto vyberu."
        if active_selection_mode
        else (
            "Tato cast ukazuje, co by pipeline vybrala pro jednotliva odberna mista pro dalsi forecast obdobi. "
            "Rezim dry_run znamena, ze se navrh jen uklada a reportuje; aktualni produkcni scoring porad pouziva "
            "globalne aktivni model."
        )
    )

    return (
        f"<h3 style='margin:22px 0 8px;'>{html.escape(section_title)}</h3>"
        "<p style='margin:0 0 10px;color:#57606a;font-size:13px;'>"
        f"{html.escape(section_description)}"
        "</p>"
        "<table style='border-collapse:collapse;font-size:14px;margin-bottom:14px;'>"
        f"{summary_table_rows}"
        "</table>"
        "<table style='border-collapse:collapse;font-size:14px;margin-bottom:14px;'>"
        "<tr>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Navrzeny model</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Pocet mist</th>"
        "</tr>"
        f"{selected_model_rows}"
        "</table>"
        f"{_build_selected_snapshot_summary_explanation_html(selection_mode)}"
        "<h4 style='margin:14px 0 6px;'>Proc nektera mista zustala na globalnim modelu</h4>"
        f"{fallback_html}"
        "<h4 style='margin:14px 0 6px;'>Measured-only modely, ktere by historicky vyhraly</h4>"
        f"{measured_only_html}"
        "<h4 style='margin:14px 0 6px;'>Kontrola nejhorsich navrzenych vyberu podle WAPE</h4>"
        f"{worst_html}"
    )


def _build_selected_snapshot_summary_explanation_html(selection_mode: object) -> str:
    active_selection_mode = str(selection_mode).strip().lower() == "active"
    mode_description = (
        "active znamena, ze ulozena rozhodnuti slouzi jako produkcni zdroj per-misto profilu pro pristi forecast obdobi."
        if active_selection_mode
        else "dry_run znamena, ze pipeline pouze ulozi a reportuje navrh. Produkcni scoring se tim zatim nemeni."
    )
    title = (
        "Co znamenaji souhrnne active udaje"
        if active_selection_mode
        else "Co znamenaji souhrnne dry-run udaje"
    )
    items = (
        ("Rezim vyberu", mode_description),
        ("Obdobi, pro ktere vyber plati", "Forecast obdobi, pro ktere je vyber modelu pripraveny."),
        ("Odberna mista s navrhem", "Pocet mist, pro ktera existuje navrh vybraneho modelu."),
        ("Ulozena rozhodnuti", "Pocet navrhu ulozenych do tabulky snapshotu pro pozdejsi vyhodnoceni."),
        ("Navrh stejny/jiny nez globalni model", "Porovnani navrhu per-misto modelu proti globalne aktivnimu modelu."),
        ("Fallback", "Bezpecny navrat na globalni model, kdyz pro misto chybi pouzitelne metriky nebo neni vhodny eligible kandidat."),
    )
    return _build_explanation_block_html(
        title,
        items,
    )


def _snapshot_differs_from_global(row: dict[str, object]) -> bool:
    return (
        row.get("selected_model_version") != row.get("global_model_version")
        or row.get("selected_model_key") != row.get("global_model_key")
    )


def _snapshot_uses_fallback(row: dict[str, object]) -> bool:
    fallback_reason = str(row.get("fallback_reason") or "none")
    return bool(row.get("uses_fallback")) or fallback_reason != "none"


def _count_snapshot_selected_models(
    snapshot_rows: list[dict[str, object]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in snapshot_rows:
        label = _format_snapshot_selected_model_label(row)
        counts[label] = counts.get(label, 0) + 1
    return counts


def _count_snapshot_fallback_reasons(
    fallback_rows: list[dict[str, object]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in fallback_rows:
        reason = _format_fallback_reason(row.get("fallback_reason"))
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _count_measured_only_would_win(device_candidate_rows: object) -> dict[str, int]:
    if not isinstance(device_candidate_rows, list):
        return {}

    counts: dict[str, int] = {}
    for row in device_candidate_rows:
        if not isinstance(row, dict):
            continue
        if not row.get("best_for_identifier"):
            continue
        if bool(row.get("selection_enabled", True)):
            continue
        label = _format_device_model_label(row)
        counts[label] = counts.get(label, 0) + 1
    return counts


def _build_count_rows(counts: dict[str, int]) -> str:
    return "".join(
        (
            "<tr>"
            f"<td style='padding:6px 10px;border:1px solid #d0d7de;'>{html.escape(label)}</td>"
            f"<td style='padding:6px 10px;border:1px solid #d0d7de;text-align:right;'>{count}</td>"
            "</tr>"
        )
        for label, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    )


def _select_worst_selected_snapshot_rows(
    snapshot_rows: list[dict[str, object]],
    *,
    limit: int,
) -> list[dict[str, object]]:
    eligible_rows = [
        row
        for row in snapshot_rows
        if not _snapshot_uses_fallback(row)
        and _snapshot_metric_value(row, "wape") is not None
    ]
    return sorted(
        eligible_rows,
        key=lambda row: (
            -float(_snapshot_metric_value(row, "wape") or 0.0),
            str(row.get("identifier", "")),
        ),
    )[:limit]


def _build_selected_snapshot_worst_row(row: dict[str, object]) -> str:
    return (
        "<tr>"
        f"<td style='padding:7px 10px;border:1px solid #d0d7de;'>{html.escape(str(row.get('identifier', '-')))}</td>"
        f"<td style='padding:7px 10px;border:1px solid #d0d7de;'>{html.escape(_format_snapshot_selected_model_label(row))}</td>"
        f"<td style='padding:7px 10px;border:1px solid #d0d7de;text-align:right;'>{_format_percentage(_snapshot_metric_value(row, 'wape'))}</td>"
        f"<td style='padding:7px 10px;border:1px solid #d0d7de;text-align:right;'>{_format_metric(_snapshot_metric_value(row, 'mae'))}</td>"
        f"<td style='padding:7px 10px;border:1px solid #d0d7de;text-align:right;'>{_format_percentage(_snapshot_metric_value(row, 'coverage'))}</td>"
        f"<td style='padding:7px 10px;border:1px solid #d0d7de;text-align:right;'>{_format_optional_int(_snapshot_metric_value(row, 'matched_validation_count'))}</td>"
        "</tr>"
    )


def _snapshot_metric_value(row: dict[str, object], metric_key: str) -> object:
    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        return None
    return metrics.get(metric_key)


def _format_snapshot_selected_model_label(row: dict[str, object]) -> str:
    return (
        f"{row.get('selected_model_name', 'Model')} "
        f"(v{row.get('selected_model_version', '-')})"
    )


def _format_device_model_label(row: dict[str, object]) -> str:
    model_label = f"{row.get('model_name', 'Model')} (v{row.get('model_version', '-')})"
    if not bool(row.get("selection_enabled", True)):
        model_label = f"{model_label} - measured only"
    return model_label


def _format_fallback_reason(value: object) -> str:
    reason = str(value or "none")
    return reason.replace("_", " ")


def _format_forecast_period(forecast_period: object) -> str:
    if not isinstance(forecast_period, dict):
        return "-"
    label = forecast_period.get("label")
    if label:
        return str(label)
    start = forecast_period.get("start")
    end = forecast_period.get("end")
    if start is None or end is None:
        return "-"
    return f"{_format_datetime(start)} - {_format_datetime(end)}"


def _build_metric_explanation_html() -> str:
    return (
        "<div style='font-size:13px;line-height:1.45;margin-top:14px;color:#57606a;max-width:980px;'>"
        "<p style='margin:0 0 6px;'><strong>Vysvetleni metrik:</strong></p>"
        "<p style='margin:0 0 4px;'><strong>MAE</strong> je prumerna absolutni chyba predikce. "
        "Nizsi hodnota znamena presnejsi model.</p>"
        "<p style='margin:0 0 4px;'><strong>RMSE</strong> je odmocnina prumerne kvadraticke chyby. "
        "Vice zvyraznuje velke odchylky, proto je citlivejsi na spicky.</p>"
        "<p style='margin:0 0 4px;'><strong>Bias</strong> je prumerna podepsana chyba "
        "(skutecna spotreba minus predikce). Kladna hodnota znamena, ze model spotrebu spis podhodnocuje; "
        "zaporna hodnota znamena, ze ji spis nadhodnocuje.</p>"
        "<p style='margin:0 0 4px;'><strong>Rolling</strong> metriky jsou agregovane pres tydenni backtest foldy "
        "a slouzi pro stabilnejsi porovnani kandidatu v case.</p>"
        "<p style='margin:0;'><strong>Measured only</strong> znamena, ze kandidat je mereny v reportu, "
        "ale neni zpusobily pro automaticke nasazeni jako aktivni model.</p>"
        "</div>"
    )
