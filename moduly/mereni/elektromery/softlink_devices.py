from __future__ import annotations

import asyncio
import concurrent.futures
import html
import inspect
import sys
import warnings
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from typing import Any, Iterable, Mapping

from decouple import config

from app.channels.email import send_email_outlook
from core.db.connect import get_session_ms
from moduly.mereni.elektromery.database.models import Elektromer_areal_Zarizeni
from moduly.mereni.vodomery.reporting._email_config import (
    filter_placeholder_recipients,
    load_report_recipients,
    sanitize_sender_alias,
)


DEFAULT_NEW_DEVICE_REPORT_RECIPIENTS = "ops@example.com"
DEFAULT_NEW_DEVICE_REPORT_SENDER_ALIAS = "upozorneni@example.com"


class ElektromerySoftlinkDeviceError(RuntimeError):
    """Raised when SOFTLINK device discovery or persistence fails."""


@dataclass(frozen=True)
class SoftlinkDeviceCandidate:
    softlink_id: int
    description: str | None
    serial_number: int | None
    meter_type: str | None
    plomb: str | None
    initial_value: float | None
    mis_id: int | None
    met_id: int | None
    valid_from: datetime | None
    valid_to: datetime | None
    calibration_valid_until: datetime | None
    raw_payload: dict[str, object]


@dataclass(frozen=True)
class SoftlinkDeviceDiscoveryReport:
    generated_at: datetime
    source_status: int | None
    total_softlink_devices: int
    matched_device_count: int
    new_devices: tuple[SoftlinkDeviceCandidate, ...]

    @property
    def new_device_count(self) -> int:
        return len(self.new_devices)

    def remove_device(self, softlink_id: int) -> "SoftlinkDeviceDiscoveryReport":
        filtered_devices = tuple(device for device in self.new_devices if device.softlink_id != softlink_id)
        removed_count = len(self.new_devices) - len(filtered_devices)
        if removed_count <= 0:
            return self
        return replace(
            self,
            matched_device_count=self.matched_device_count + removed_count,
            new_devices=filtered_devices,
        )


@dataclass(frozen=True)
class SoftlinkDeviceSaveResult:
    action: str
    identifikace: str
    softlink_id: int


def _default_softlink_fetcher(*, headless: bool = True):
    from moduly.mereni.elektromery.SOFTLINK.SOFTLINK_data_zarizeni import SOFTLINK_dotaz_zarizeni

    return SOFTLINK_dotaz_zarizeni(headless=headless)


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_int(value: object, *, field_label: str, strict: bool = True) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        if strict:
            raise ElektromerySoftlinkDeviceError(f"Pole {field_label} nema platnou ciselnu hodnotu.")
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value:
            return None
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError as exc:
        if not strict:
            return None
        raise ElektromerySoftlinkDeviceError(f"Pole {field_label} nema platnou ciselnu hodnotu.") from exc


def _normalize_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and value == value:
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_datetime(value: object, *, field_label: str | None = None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, (int, float)) and value == value:
        timestamp = float(value)
        if abs(timestamp) > 10_000_000_000:
            timestamp = timestamp / 1000.0
        return datetime.fromtimestamp(timestamp)

    text = str(value).strip()
    if not text:
        return None

    for parser in (
        lambda raw: datetime.fromisoformat(raw),
        lambda raw: datetime.strptime(raw, "%d.%m.%Y"),
        lambda raw: datetime.strptime(raw, "%d.%m.%Y %H:%M"),
        lambda raw: datetime.strptime(raw, "%Y-%m-%d"),
        lambda raw: datetime.strptime(raw, "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            return parser(text)
        except ValueError:
            continue

    if field_label is None:
        return None
    raise ElektromerySoftlinkDeviceError(f"Pole {field_label} nema platny format data.")


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%d.%m.%Y")


def build_candidate_form_defaults(candidate: SoftlinkDeviceCandidate) -> dict[str, object]:
    return {
        "identifikace": "",
        "seriove_cislo": "" if candidate.serial_number is None else str(candidate.serial_number),
        "ean": "",
        "pozice": "",
        "podruzny": "",
        "mistnost": "",
        "umisteni": candidate.description or "",
        "napaji": "",
        "koncovy_odberatel": "",
        "platnost_cejchu": _format_datetime(candidate.calibration_valid_until),
        "jistic": "",
        "typ_merice": candidate.meter_type or "",
        "rozvadec": "",
        "typ_tarifu": "",
        "platnost_od": _format_datetime(candidate.valid_from),
        "platnost_do": _format_datetime(candidate.valid_to),
        "plomb": candidate.plomb or "",
        "mis_id": "" if candidate.mis_id is None else str(candidate.mis_id),
        "met_id": "" if candidate.met_id is None else str(candidate.met_id),
        "foto": "",
    }


def _candidate_from_payload(payload: Mapping[str, object]) -> SoftlinkDeviceCandidate | None:
    softlink_id = _normalize_int(payload.get("me_id"), field_label="softlink_id")
    if softlink_id is None:
        return None

    return SoftlinkDeviceCandidate(
        softlink_id=softlink_id,
        description=_normalize_text(payload.get("me_desc")),
        serial_number=_normalize_int(payload.get("me_serial"), field_label="seriove_cislo", strict=False),
        meter_type=_normalize_text(payload.get("me_typ_pzn")),
        plomb=_normalize_text(payload.get("me_plom")),
        initial_value=_normalize_float(payload.get("me_zapoc")),
        mis_id=_normalize_int(payload.get("mis_id"), field_label="mis_id", strict=False),
        met_id=_normalize_int(payload.get("met_id"), field_label="met_id", strict=False),
        valid_from=_normalize_datetime(payload.get("me_od")),
        valid_to=_normalize_datetime(payload.get("me_do")),
        calibration_valid_until=_normalize_datetime(payload.get("me_over")),
        raw_payload=dict(payload),
    )


def normalize_softlink_device_response(response: object) -> tuple[int | None, tuple[SoftlinkDeviceCandidate, ...]]:
    source_status = None
    payload_items: object = response
    if isinstance(response, Mapping):
        raw_status = response.get("status")
        source_status = _normalize_int(raw_status, field_label="status") if raw_status is not None else None
        payload_items = response.get("data", ())

    if payload_items is None:
        payload_items = ()
    if not isinstance(payload_items, Iterable) or isinstance(payload_items, (str, bytes, Mapping)):
        raise ElektromerySoftlinkDeviceError("SOFTLINK nevratil ocekavany seznam zarizeni.")

    devices_by_softlink_id: dict[int, SoftlinkDeviceCandidate] = {}
    for item in payload_items:
        if not isinstance(item, Mapping):
            continue
        candidate = _candidate_from_payload(item)
        if candidate is None or candidate.softlink_id in devices_by_softlink_id:
            continue
        devices_by_softlink_id[candidate.softlink_id] = candidate

    devices = tuple(sorted(devices_by_softlink_id.values(), key=lambda candidate: candidate.softlink_id))
    return source_status, devices


def _invoke_softlink_fetcher(fetch_fn) -> object:
    try:
        signature = inspect.signature(fetch_fn)
    except (TypeError, ValueError):
        signature = None
    if signature is not None and "headless" in signature.parameters:
        return fetch_fn(headless=True)
    return fetch_fn()


def _run_softlink_fetcher_windows_worker(fetch_fn) -> object:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        original_policy = asyncio.get_event_loop_policy()
        windows_policy_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
        try:
            if windows_policy_cls is not None:
                asyncio.set_event_loop_policy(windows_policy_cls())
            return _invoke_softlink_fetcher(fetch_fn)
        finally:
            asyncio.set_event_loop_policy(original_policy)


def fetch_softlink_device_inventory(fetch_fn=None) -> object:
    resolved_fetch_fn = _default_softlink_fetcher if fetch_fn is None else fetch_fn
    try:
        if sys.platform == "win32":
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(_run_softlink_fetcher_windows_worker, resolved_fetch_fn).result()
        return _invoke_softlink_fetcher(resolved_fetch_fn)
    except ElektromerySoftlinkDeviceError:
        raise
    except Exception as exc:
        raise ElektromerySoftlinkDeviceError(
            f"Nepodarilo se nacist seznam zarizeni ze SOFTLINK: {exc.__class__.__name__}."
        ) from exc


def load_existing_softlink_ids(session_factory=get_session_ms) -> tuple[int, ...]:
    session = session_factory()
    try:
        rows = (
            session.query(Elektromer_areal_Zarizeni.softlink_id)
            .filter(Elektromer_areal_Zarizeni.softlink_id.is_not(None))
            .all()
        )
        existing_ids = sorted(
            {
                int(row[0])
                for row in rows
                if row[0] is not None
            }
        )
        return tuple(existing_ids)
    finally:
        session.close()


def discover_new_softlink_devices(
    *,
    fetch_fn=None,
    session_factory=get_session_ms,
    generated_at: datetime | None = None,
) -> SoftlinkDeviceDiscoveryReport:
    raw_response = fetch_softlink_device_inventory(fetch_fn=fetch_fn)
    source_status, all_devices = normalize_softlink_device_response(raw_response)
    existing_ids = set(load_existing_softlink_ids(session_factory=session_factory))
    new_devices = tuple(device for device in all_devices if device.softlink_id not in existing_ids)
    matched_device_count = len(all_devices) - len(new_devices)
    return SoftlinkDeviceDiscoveryReport(
        generated_at=generated_at or datetime.now(),
        source_status=source_status,
        total_softlink_devices=len(all_devices),
        matched_device_count=matched_device_count,
        new_devices=new_devices,
    )


def describe_candidate(candidate: SoftlinkDeviceCandidate) -> str:
    description_parts = []
    if candidate.description:
        description_parts.append(candidate.description)
    if candidate.serial_number is not None:
        description_parts.append(f"S/N {candidate.serial_number}")
    if candidate.meter_type:
        description_parts.append(candidate.meter_type)
    return " | ".join(description_parts) if description_parts else f"SOFTLINK ID {candidate.softlink_id}"


def build_new_softlink_devices_email_body(report: SoftlinkDeviceDiscoveryReport) -> str:
    header = (
        "<p style='margin:0 0 16px;'>"
        "Tydenni kontrola SOFTLINK zarizeni byla dokoncena. "
        f"V SOFTLINK je evidovano <strong>{report.total_softlink_devices}</strong> zarizeni, "
        f"v MS tabulce je sparovano <strong>{report.matched_device_count}</strong> a "
        f"novych je <strong>{report.new_device_count}</strong>."
        "</p>"
    )

    if not report.new_devices:
        return (
            "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328;'>"
            "<h2 style='margin:0 0 12px;'>Tydenni kontrola novych elektromeru</h2>"
            f"{header}"
            "<p style='margin:0;'>V SOFTLINK nebyla nalezena zadna nova softlink_id mimo dbo.Zarizeni_elektromery.</p>"
            "</body></html>"
        )

    table_rows = "".join(
        (
            "<tr>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;'>{device.softlink_id}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;'>{html.escape(device.description or '-')}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{html.escape(str(device.serial_number or '-'))}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;'>{html.escape(device.meter_type or '-')}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{html.escape(str(device.mis_id or '-'))}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{html.escape(str(device.met_id or '-'))}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;'>{html.escape(_format_datetime(device.valid_from) or '-')}</td>"
            "</tr>"
        )
        for device in report.new_devices
    )

    return (
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328;'>"
        "<h2 style='margin:0 0 12px;'>Tydenni kontrola novych elektromeru</h2>"
        f"{header}"
        "<p style='margin:0 0 16px;'>Nova zarizeni je potreba doplnit do tabulky <strong>dbo.Zarizeni_elektromery</strong>.</p>"
        "<table style='border-collapse:collapse;font-size:14px;min-width:920px;'>"
        "<tr>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Softlink ID</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Popis</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Sériové číslo</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Typ měřiče</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>MIS ID</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>MET ID</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Platnost od</th>"
        "</tr>"
        f"{table_rows}"
        "</table>"
        "</body></html>"
    )


def _load_recipients() -> tuple[str, ...]:
    return load_report_recipients(
        "ELEKTROMERY_NEW_DEVICES_REPORT_RECIPIENTS",
        default=DEFAULT_NEW_DEVICE_REPORT_RECIPIENTS,
        fallback_env_keys=("ELEKTROMERY_WEEKLY_BRANCH_REPORT_RECIPIENTS",),
        error_cls=ElektromerySoftlinkDeviceError,
    )


def _resolve_sender_alias() -> str | None:
    return sanitize_sender_alias(
        config(
            "ELEKTROMERY_NEW_DEVICES_REPORT_SENDER_ALIAS",
            default=config(
                "ELEKTROMERY_WEEKLY_BRANCH_REPORT_SENDER_ALIAS",
                default=config("O_EMAIL_UPOZORNENI", default=DEFAULT_NEW_DEVICE_REPORT_SENDER_ALIAS),
            ),
        ),
        context_label="ELEKTROMERY_NEW_DEVICES_REPORT_SENDER_ALIAS",
    )


def send_weekly_new_elektromery_report(
    *,
    recipients: tuple[str, ...] | None = None,
    fetch_fn=None,
    session_factory=get_session_ms,
) -> dict[str, object]:
    report = discover_new_softlink_devices(fetch_fn=fetch_fn, session_factory=session_factory)
    resolved_recipients = filter_placeholder_recipients(
        recipients if recipients is not None else _load_recipients(),
        context_label="send_weekly_new_elektromery_report",
    )
    subject = (
        "Elektromery | tydenni kontrola novych elektromeru | "
        f"{report.generated_at.strftime('%d.%m.%Y')}"
    )
    if not resolved_recipients:
        return {
            "title": subject,
            "recipient_count": 0,
            "recipients": (),
            "total_softlink_devices": report.total_softlink_devices,
            "matched_device_count": report.matched_device_count,
            "new_device_count": report.new_device_count,
            "skipped": True,
            "skip_reason": "no_sendable_recipients",
        }

    body = build_new_softlink_devices_email_body(report)
    sender_alias = _resolve_sender_alias()
    for recipient in resolved_recipients:
        send_email_outlook(
            email_receiver=recipient,
            subject=subject,
            body=body,
            sender_alias=sender_alias,
            is_html=True,
        )

    return {
        "title": subject,
        "recipient_count": len(resolved_recipients),
        "recipients": resolved_recipients,
        "total_softlink_devices": report.total_softlink_devices,
        "matched_device_count": report.matched_device_count,
        "new_device_count": report.new_device_count,
    }


def save_new_softlink_device(
    candidate: SoftlinkDeviceCandidate,
    form_values: Mapping[str, object],
    *,
    session_factory=get_session_ms,
) -> SoftlinkDeviceSaveResult:
    identifikace = _normalize_text(form_values.get("identifikace"))
    if not identifikace:
        raise ElektromerySoftlinkDeviceError("Pole Identifikace je povinne.")

    session = session_factory()
    try:
        existing_by_softlink = (
            session.query(Elektromer_areal_Zarizeni)
            .filter(Elektromer_areal_Zarizeni.softlink_id == candidate.softlink_id)
            .one_or_none()
        )
        if existing_by_softlink is not None:
            return SoftlinkDeviceSaveResult(
                action="already_exists",
                identifikace=str(existing_by_softlink.identifikace),
                softlink_id=candidate.softlink_id,
            )

        existing_by_ident = (
            session.query(Elektromer_areal_Zarizeni)
            .filter(Elektromer_areal_Zarizeni.identifikace == identifikace)
            .one_or_none()
        )
        if existing_by_ident is not None and existing_by_ident.softlink_id not in (None, candidate.softlink_id):
            raise ElektromerySoftlinkDeviceError(
                "Identifikace uz v dbo.Zarizeni_elektromery existuje s jinym softlink_id."
            )

        row = existing_by_ident
        action = "updated" if row is not None else "inserted"
        if row is None:
            row = Elektromer_areal_Zarizeni(identifikace=identifikace)
            session.add(row)

        row.identifikace = identifikace
        row.seriove_cislo = _normalize_int(form_values.get("seriove_cislo"), field_label="Sériové číslo")
        row.softlink_id = candidate.softlink_id
        row.EAN = _normalize_int(form_values.get("ean"), field_label="EAN")
        row.pozice = _normalize_text(form_values.get("pozice"))
        row.podruzny = _normalize_text(form_values.get("podruzny"))
        row.mistnost = _normalize_text(form_values.get("mistnost"))
        row.umisteni = _normalize_text(form_values.get("umisteni"))
        row.napaji = _normalize_text(form_values.get("napaji"))
        row.koncovy_odberatel = _normalize_text(form_values.get("koncovy_odberatel"))
        row.platnost_cejchu = _normalize_datetime(form_values.get("platnost_cejchu"), field_label="Platnost cejchu")
        row.jistic = _normalize_text(form_values.get("jistic"))
        row.typ_merice = _normalize_text(form_values.get("typ_merice"))
        row.rozvadec = _normalize_text(form_values.get("rozvadec"))
        row.typ_tarifu = _normalize_text(form_values.get("typ_tarifu"))
        row.platnost_od = _normalize_datetime(form_values.get("platnost_od"), field_label="Platnost od")
        row.platnost_do = _normalize_datetime(form_values.get("platnost_do"), field_label="Platnost do")
        row.plomb = _normalize_text(form_values.get("plomb"))
        row.mis_id = _normalize_int(form_values.get("mis_id"), field_label="MIS ID")
        row.met_id = _normalize_int(form_values.get("met_id"), field_label="MET ID")
        row.foto = _normalize_text(form_values.get("foto"))

        session.commit()
        return SoftlinkDeviceSaveResult(
            action=action,
            identifikace=identifikace,
            softlink_id=candidate.softlink_id,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
