from __future__ import annotations

import datetime
import re
import unicodedata
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from pypdf import PdfReader

from moduly.mereni.vodomery.SCVK.SCVK_data_z_dotazu import paths as SCVK_PATHS


DATE_PATTERN = r"\d{1,2}\.\d{1,2}\.\d{4}"
DATE_RANGE_PATTERNS: tuple[tuple[int, re.Pattern[str]], ...] = (
    (
        120,
        re.compile(
            rf"(?:fakturovan[eé]|z[uú]čtovac[ií]|zuctovaci)\s+obdob[ií][^0-9]{{0,40}}"
            rf"({DATE_PATTERN})\s*(?:-|–|—|do)\s*({DATE_PATTERN})",
            re.IGNORECASE,
        ),
    ),
    (
        100,
        re.compile(
            rf"obdob[ií][^0-9]{{0,20}}od[^0-9]{{0,10}}({DATE_PATTERN})[^0-9]{{0,20}}do[^0-9]{{0,10}}({DATE_PATTERN})",
            re.IGNORECASE,
        ),
    ),
    (
        80,
        re.compile(
            rf"(?:fakturovan[eé]|z[uú]čtovac[ií]|zuctovaci)[^0-9]{{0,40}}({DATE_PATTERN})\s*(?:-|–|—)\s*({DATE_PATTERN})",
            re.IGNORECASE,
        ),
    ),
)
CONSUMPTION_PATTERNS: tuple[tuple[int, re.Pattern[str]], ...] = (
    (
        140,
        re.compile(
            r"(?:celkov[aá]\s+spot[řr]eba|fakturovan[eé]\s+(?:mno[zž]stv[ií]|spot[řr]eba)|"
            r"odebran[eé]\s+mno[zž]stv[ií]|dodan[eé]\s+mno[zž]stv[ií])"
            r"[^0-9]{0,24}([0-9]+(?:[ \u00a0][0-9]{3})*(?:[,.][0-9]+)?)\s*m[3³]",
            re.IGNORECASE,
        ),
    ),
    (
        110,
        re.compile(
            r"(?:mno[zž]stv[ií]|spot[řr]eba)[^0-9]{0,18}([0-9]+(?:[ \u00a0][0-9]{3})*(?:[,.][0-9]+)?)\s*m[3³]",
            re.IGNORECASE,
        ),
    ),
    (
        90,
        re.compile(
            r"(?:vodn[eé]|pitn[aá]\s+voda)[^0-9]{0,24}([0-9]+(?:[ \u00a0][0-9]{3})*(?:[,.][0-9]+)?)\s*m[3³]",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class ParsedScvkInvoice:
    period_start: datetime.date | None
    period_end: datetime.date | None
    total_consumption_m3: float | None
    billing_ident: str | None = None
    raw_text: str = ""
    notes: tuple[str, ...] = ()


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n".join(page for page in pages if page).strip()


def parse_scvk_invoice_pdf(pdf_bytes: bytes) -> ParsedScvkInvoice:
    try:
        text = extract_text_from_pdf_bytes(pdf_bytes)
    except Exception as exc:
        return ParsedScvkInvoice(
            period_start=None,
            period_end=None,
            total_consumption_m3=None,
            raw_text="",
            notes=(f"Nepodařilo se přečíst obsah PDF: {exc}",),
        )
    return parse_scvk_invoice_text(text)


def parse_scvk_invoice_text(text: str) -> ParsedScvkInvoice:
    normalized_text = _normalize_text(text)
    period_start, period_end = _extract_period(normalized_text)
    total_consumption = _extract_total_consumption(normalized_text)
    billing_ident = _detect_billing_ident(normalized_text)

    notes: list[str] = []
    if period_start is None or period_end is None:
        notes.append("Nepodařilo se spolehlivě určit fakturační období z PDF.")
    if total_consumption is None:
        notes.append("Nepodařilo se spolehlivě určit celkovou spotřebu z PDF.")

    return ParsedScvkInvoice(
        period_start=period_start,
        period_end=period_end,
        total_consumption_m3=total_consumption,
        billing_ident=billing_ident,
        raw_text=normalized_text,
        notes=tuple(notes),
    )


def apply_invoice_consumption_to_payload(
    payload: dict[str, Any],
    invoice_consumption_m3: float | None,
) -> dict[str, Any]:
    result = dict(payload)
    raw_billing_consumption = _normalize_optional_float(payload.get("billing_consumption"))
    normalized_invoice_consumption = _normalize_optional_float(invoice_consumption_m3)
    submeter_consumption_total = _normalize_optional_float(payload.get("submeter_consumption_total")) or 0.0

    result["reference_billing_consumption"] = raw_billing_consumption
    result["invoice_billing_consumption"] = normalized_invoice_consumption
    result["billing_consumption_source"] = (
        "invoice_pdf" if normalized_invoice_consumption is not None else "measurements"
    )

    if normalized_invoice_consumption is None:
        result["device_rows"] = [dict(row) for row in payload.get("device_rows", [])]
        result["assignment_rows"] = [dict(row) for row in payload.get("assignment_rows", [])]
        result["segment_rows"] = [dict(row) for row in payload.get("segment_rows", [])]
        return result

    result["billing_consumption"] = normalized_invoice_consumption
    result["difference"] = round(normalized_invoice_consumption - submeter_consumption_total, 3)
    result["coverage_percent"] = (
        round(submeter_consumption_total / normalized_invoice_consumption * 100, 1)
        if normalized_invoice_consumption > 0
        else None
    )

    device_rows: list[dict[str, Any]] = []
    for row in payload.get("device_rows", []):
        updated_row = dict(row)
        device_consumption = _normalize_optional_float(row.get("spotreba")) or 0.0
        updated_row["podil_na_fakturacnim_procent"] = (
            round(device_consumption / normalized_invoice_consumption * 100, 1)
            if normalized_invoice_consumption > 0
            else None
        )
        updated_row["rozpoctena_fakturacni_spotreba"] = (
            round(normalized_invoice_consumption * device_consumption / submeter_consumption_total, 3)
            if submeter_consumption_total > 0
            else None
        )
        device_rows.append(updated_row)
    result["device_rows"] = device_rows

    segment_rows: list[dict[str, Any]] = []
    for row in payload.get("segment_rows", []):
        updated_row = dict(row)
        segment_submeter_consumption = _normalize_optional_float(row.get("submeter_consumption")) or 0.0
        allocated_segment_consumption = (
            round(normalized_invoice_consumption * segment_submeter_consumption / submeter_consumption_total, 3)
            if submeter_consumption_total > 0
            else None
        )
        updated_row["billing_consumption"] = allocated_segment_consumption
        updated_row["difference"] = (
            round(allocated_segment_consumption - segment_submeter_consumption, 3)
            if allocated_segment_consumption is not None
            else None
        )
        segment_rows.append(updated_row)
    result["segment_rows"] = segment_rows
    result["assignment_rows"] = [dict(row) for row in payload.get("assignment_rows", [])]

    return result


def _normalize_text(text: str) -> str:
    normalized = (text or "").replace("\r", "\n").replace("\xa0", " ")
    normalized = normalized.replace("m3", "m³").replace("M3", "m³")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{2,}", "\n", normalized)
    return normalized.strip()


def _extract_period(text: str) -> tuple[datetime.date | None, datetime.date | None]:
    best_match: tuple[int, datetime.date, datetime.date] | None = None
    for score, pattern in DATE_RANGE_PATTERNS:
        for match in pattern.finditer(text):
            start_date = _parse_date(match.group(1))
            end_date = _parse_date(match.group(2))
            if start_date is None or end_date is None:
                continue
            if end_date < start_date:
                start_date, end_date = end_date, start_date
            duration_days = (end_date - start_date).days
            if duration_days < 0 or duration_days > 400:
                continue
            candidate = (score, start_date, end_date)
            if best_match is None or candidate[0] > best_match[0]:
                best_match = candidate
        if best_match is not None:
            break
    if best_match is None:
        return None, None
    return best_match[1], best_match[2]


def _extract_total_consumption(text: str) -> float | None:
    best_match: tuple[int, float] | None = None
    for score, pattern in CONSUMPTION_PATTERNS:
        for match in pattern.finditer(text):
            value = _parse_czech_number(match.group(1))
            if value is None or value < 0:
                continue
            candidate = (score, value)
            if best_match is None or candidate[0] > best_match[0]:
                best_match = candidate
        if best_match is not None:
            break
    return None if best_match is None else best_match[1]


def _detect_billing_ident(text: str) -> str | None:
    normalized_ascii = _normalize_ascii(text)
    best_ident: str | None = None
    best_score = 0
    for ident, values in SCVK_PATHS.items():
        score = 0
        odberne_misto = str(values.get("odberne misto", "")).strip()
        cislo_vodomeru = str(values.get("cislo vodomeru", "")).strip()
        cislo_hlavy = str(values.get("cislo hlavy", "")).strip()
        oznaceni = _normalize_ascii(str(values.get("oznaceni", "")).strip())

        if odberne_misto and odberne_misto in text:
            score += 90
        if cislo_vodomeru and cislo_vodomeru in text:
            score += 80
        if cislo_hlavy and cislo_hlavy.upper() in text.upper():
            score += 120
        if oznaceni and oznaceni in normalized_ascii:
            score += 70

        if score > best_score:
            best_ident = ident
            best_score = score
    return best_ident


def _parse_date(value: str) -> datetime.date | None:
    try:
        return datetime.datetime.strptime(value.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def _parse_czech_number(value: str) -> float | None:
    cleaned = value.replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        return round(float(cleaned), 3)
    except ValueError:
        return None


def _normalize_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    return round(numeric_value, 3)


def _normalize_ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_only.upper()
