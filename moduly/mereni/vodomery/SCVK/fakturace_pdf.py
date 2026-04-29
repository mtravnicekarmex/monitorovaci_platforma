from __future__ import annotations

import datetime
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from pypdf import PdfReader

from moduly.mereni.vodomery.SCVK.SCVK_data_z_dotazu import paths as SCVK_PATHS


DATE_PATTERN = r"\d{1,2}\.\d{1,2}\.\d{4}"
NUMBER_PATTERN = r"[0-9]+(?:[ \u00a0][0-9]{3})*(?:[,.][0-9]+)?"
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
PRICE_KEYWORD_PATTERN = re.compile(
    r"(?:vodn[eé]|sto[cč]n[eé]|pitn[aá]\s+voda|odpadn[ií]\s+voda)",
    re.IGNORECASE,
)
PRICE_WITH_UNIT_PATTERN = re.compile(
    rf"({NUMBER_PATTERN})\s*(?:K[čc]\s*/\s*m[3³]|K[čc]\s*/\s*m\s*3|K[čc]/m[3³])",
    re.IGNORECASE,
)
PRICE_AFTER_M3_PATTERN = re.compile(
    rf"m[3³]\D{{0,30}}({NUMBER_PATTERN})",
    re.IGNORECASE,
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
class ParsedScvkPriceInterval:
    start_date: datetime.date
    end_date: datetime.date
    price_per_m3: float


@dataclass(frozen=True)
class ParsedScvkInvoice:
    period_start: datetime.date | None
    period_end: datetime.date | None
    total_consumption_m3: float | None
    billing_ident: str | None = None
    price_intervals: tuple[ParsedScvkPriceInterval, ...] = ()
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
    price_intervals = _extract_price_intervals(normalized_text)

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
        price_intervals=price_intervals,
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
        if isinstance(row.get("device_consumptions"), list):
            updated_device_consumptions: list[dict[str, Any]] = []
            for device_consumption_row in row.get("device_consumptions", []):
                if not isinstance(device_consumption_row, dict):
                    continue
                updated_device_consumption_row = dict(device_consumption_row)
                device_consumption = _normalize_optional_float(
                    updated_device_consumption_row.get("spotreba")
                ) or 0.0
                updated_device_consumption_row["billing_consumption"] = (
                    round(normalized_invoice_consumption * device_consumption / submeter_consumption_total, 3)
                    if submeter_consumption_total > 0
                    else None
                )
                updated_device_consumptions.append(updated_device_consumption_row)
            updated_row["device_consumptions"] = updated_device_consumptions
        segment_rows.append(updated_row)
    result["segment_rows"] = segment_rows
    result["assignment_rows"] = [dict(row) for row in payload.get("assignment_rows", [])]

    return result


def apply_price_intervals_to_payload(
    payload: dict[str, Any],
    price_intervals: Iterable[Any],
) -> dict[str, Any]:
    result = dict(payload)
    normalized_intervals = _normalize_price_interval_inputs(price_intervals)
    result["price_intervals"] = [
        {
            "start_date": interval.start_date,
            "end_date": interval.end_date,
            "price_per_m3": interval.price_per_m3,
        }
        for interval in normalized_intervals
    ]

    if not normalized_intervals:
        result["device_rows"] = [dict(row) for row in payload.get("device_rows", [])]
        result["assignment_rows"] = [dict(row) for row in payload.get("assignment_rows", [])]
        result["segment_rows"] = [dict(row) for row in payload.get("segment_rows", [])]
        return result

    device_totals: dict[str, dict[str, float]] = {}
    total_priced_consumption = 0.0
    total_price_cost = 0.0

    for segment in payload.get("segment_rows", []):
        if not isinstance(segment, dict):
            continue
        segment_start = _coerce_datetime(segment.get("start_time"))
        segment_end_inclusive = _coerce_datetime(segment.get("end_time"))
        segment_billing_consumption = _normalize_optional_float(segment.get("billing_consumption"))
        segment_submeter_consumption = _normalize_optional_float(segment.get("submeter_consumption")) or 0.0
        if (
            segment_start is None
            or segment_end_inclusive is None
            or segment_billing_consumption is None
            or segment_billing_consumption <= 0
        ):
            continue

        segment_end = segment_end_inclusive + datetime.timedelta(seconds=1)
        segment_duration_seconds = (segment_end - segment_start).total_seconds()
        if segment_duration_seconds <= 0:
            continue

        device_consumption_rows = _extract_segment_device_consumptions(segment)
        if not device_consumption_rows:
            continue

        for price_interval in normalized_intervals:
            interval_start = datetime.datetime.combine(price_interval.start_date, datetime.time.min)
            interval_end = datetime.datetime.combine(
                price_interval.end_date + datetime.timedelta(days=1),
                datetime.time.min,
            )
            overlap_start = max(segment_start, interval_start)
            overlap_end = min(segment_end, interval_end)
            overlap_seconds = (overlap_end - overlap_start).total_seconds()
            if overlap_seconds <= 0:
                continue

            overlap_ratio = overlap_seconds / segment_duration_seconds
            for identifier, device_consumption, device_billing_consumption in device_consumption_rows:
                if not identifier:
                    continue
                allocated_device_consumption = device_billing_consumption
                if allocated_device_consumption is None:
                    if segment_submeter_consumption <= 0:
                        continue
                    allocated_device_consumption = round(
                        segment_billing_consumption * device_consumption / segment_submeter_consumption,
                        3,
                    )

                interval_consumption = allocated_device_consumption * overlap_ratio
                interval_cost = interval_consumption * price_interval.price_per_m3
                totals = device_totals.setdefault(
                    identifier,
                    {"priced_consumption": 0.0, "payment_amount": 0.0},
                )
                totals["priced_consumption"] += interval_consumption
                totals["payment_amount"] += interval_cost
                total_priced_consumption += interval_consumption
                total_price_cost += interval_cost

    device_rows: list[dict[str, Any]] = []
    for row in payload.get("device_rows", []):
        updated_row = dict(row)
        totals = device_totals.get(str(updated_row.get("identifikace", "")))
        if totals is not None:
            updated_row["priced_consumption"] = round(totals["priced_consumption"], 3)
            updated_row["payment_amount"] = round(totals["payment_amount"], 2)
        device_rows.append(updated_row)

    result["device_rows"] = device_rows
    result["assignment_rows"] = [dict(row) for row in payload.get("assignment_rows", [])]
    result["segment_rows"] = [dict(row) for row in payload.get("segment_rows", [])]
    result["priced_consumption_total"] = round(total_priced_consumption, 3)
    result["payment_amount_total"] = round(total_price_cost, 2)
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


def _extract_price_intervals(text: str) -> tuple[ParsedScvkPriceInterval, ...]:
    candidates: dict[tuple[datetime.date, datetime.date, str, float], ParsedScvkPriceInterval] = {}
    for window in _iter_price_candidate_windows(text):
        for keyword_match in PRICE_KEYWORD_PATTERN.finditer(window):
            candidate_text = window[keyword_match.start() :]
            date_matches = list(re.finditer(DATE_PATTERN, candidate_text))
            if len(date_matches) < 2:
                continue
            start_date = _parse_date(date_matches[0].group(0))
            end_date = _parse_date(date_matches[1].group(0))
            if start_date is None or end_date is None:
                continue
            if end_date < start_date:
                start_date, end_date = end_date, start_date
            if (end_date - start_date).days > 400:
                continue

            unit_price = _extract_unit_price_from_window(candidate_text[date_matches[1].end() :])
            if unit_price is None:
                continue
            charge_type = _detect_price_charge_type(keyword_match.group(0))
            candidates[(start_date, end_date, charge_type, unit_price)] = ParsedScvkPriceInterval(
                start_date=start_date,
                end_date=end_date,
                price_per_m3=unit_price,
            )

    combined: dict[tuple[datetime.date, datetime.date], float] = {}
    for candidate in candidates.values():
        key = (candidate.start_date, candidate.end_date)
        combined[key] = round(combined.get(key, 0.0) + candidate.price_per_m3, 2)

    return tuple(
        ParsedScvkPriceInterval(start_date=start_date, end_date=end_date, price_per_m3=price_per_m3)
        for (start_date, end_date), price_per_m3 in sorted(combined.items(), key=lambda item: item[0])
    )


def _iter_price_candidate_windows(text: str) -> Iterable[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    seen: set[str] = set()
    for window_size in (1, 2, 3):
        for index in range(0, max(len(lines) - window_size + 1, 0)):
            window = " ".join(lines[index : index + window_size])
            normalized_window = re.sub(r"\s+", " ", window).strip()
            if not normalized_window or normalized_window in seen:
                continue
            seen.add(normalized_window)
            yield normalized_window


def _extract_unit_price_from_window(tail: str) -> float | None:
    explicit_match = PRICE_WITH_UNIT_PATTERN.search(tail)
    if explicit_match:
        price = _parse_czech_number(explicit_match.group(1))
        if _is_plausible_unit_price(price):
            return price

    m3_match = PRICE_AFTER_M3_PATTERN.search(tail)
    if m3_match:
        price = _parse_czech_number(m3_match.group(1))
        if _is_plausible_unit_price(price):
            return price

    number_matches = [
        (_parse_czech_number(match.group(0)), match.group(0))
        for match in re.finditer(NUMBER_PATTERN, tail)
    ]
    numbers = [(value, raw_value) for value, raw_value in number_matches if value is not None]
    if len(numbers) >= 3:
        product_price = _find_price_by_amount_product(numbers)
        if product_price is not None:
            return product_price
        price = numbers[-2][0]
        if _is_plausible_unit_price(price):
            return price
    if len(numbers) >= 2:
        price = numbers[1][0]
        if _is_plausible_unit_price(price):
            return price
    return None


def _find_price_by_amount_product(numbers: list[tuple[float, str]]) -> float | None:
    values = [value for value, _ in numbers]
    for price_index in range(1, len(values) - 1):
        price = values[price_index]
        if not _is_plausible_unit_price(price):
            continue
        previous_values = values[max(0, price_index - 3) : price_index]
        following_values = values[price_index + 1 : min(len(values), price_index + 4)]
        for quantity in previous_values:
            if quantity <= 0:
                continue
            expected_amount = quantity * price
            for amount in following_values:
                if amount <= 0:
                    continue
                relative_difference = abs(expected_amount - amount) / max(amount, 1.0)
                if relative_difference <= 0.08:
                    return round(price, 2)
    return None


def _detect_price_charge_type(value: str) -> str:
    normalized = _normalize_ascii(value)
    if "STOCNE" in normalized or "ODPADNI VODA" in normalized:
        return "stocne"
    if "VODNE" in normalized or "PITNA VODA" in normalized:
        return "vodne"
    return "voda"


def _is_plausible_unit_price(value: float | None) -> bool:
    return value is not None and 0 < value <= 500


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


def _normalize_price_interval_inputs(
    price_intervals: Iterable[Any],
) -> tuple[ParsedScvkPriceInterval, ...]:
    normalized: list[ParsedScvkPriceInterval] = []
    for interval in price_intervals:
        if isinstance(interval, ParsedScvkPriceInterval):
            normalized.append(interval)
            continue
        if not isinstance(interval, dict):
            continue
        start_date = interval.get("start_date")
        end_date = interval.get("end_date")
        price_per_m3 = _normalize_optional_float(interval.get("price_per_m3"))
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime.datetime):
            end_date = end_date.date()
        if (
            not isinstance(start_date, datetime.date)
            or not isinstance(end_date, datetime.date)
            or price_per_m3 is None
            or price_per_m3 < 0
        ):
            continue
        if end_date < start_date:
            start_date, end_date = end_date, start_date
        normalized.append(
            ParsedScvkPriceInterval(
                start_date=start_date,
                end_date=end_date,
                price_per_m3=round(price_per_m3, 2),
            )
        )
    return tuple(sorted(normalized, key=lambda item: (item.start_date, item.end_date)))


def _extract_segment_device_consumptions(
    segment: dict[str, Any],
) -> list[tuple[str, float, float | None]]:
    device_consumption_rows: list[tuple[str, float, float | None]] = []
    raw_rows = segment.get("device_consumptions")
    if isinstance(raw_rows, list):
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                continue
            identifier = str(raw_row.get("identifikace", "") or "")
            consumption = _normalize_optional_float(raw_row.get("spotreba")) or 0.0
            billing_consumption = _normalize_optional_float(raw_row.get("billing_consumption"))
            device_consumption_rows.append((identifier, consumption, billing_consumption))
    if device_consumption_rows:
        return device_consumption_rows

    active_devices = segment.get("active_devices")
    if isinstance(active_devices, list) and len(active_devices) == 1:
        consumption = _normalize_optional_float(segment.get("submeter_consumption")) or 0.0
        return [(str(active_devices[0]), consumption, None)]
    return []


def _coerce_datetime(value: Any) -> datetime.datetime | None:
    if isinstance(value, datetime.datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time.min)
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _normalize_ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_only.upper()
