from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, Mapping

from moduly.apps.dashboard.api_client import (
    get_kalorimetry_devices,
    get_plynomery_devices,
    get_vodomery_devices,
    list_kalorimetry_outlier_reviews,
    list_plynomery_outlier_reviews,
    list_vodomery_outlier_reviews,
    update_kalorimetry_outlier_review,
    update_plynomery_outlier_review,
    update_vodomery_outlier_review,
)


STATUS_OPTIONS = ("ALL", "PENDING", "CONFIRMED_OUTLIER", "CONFIRMED_CONSUMPTION")
STATUS_SAVE_OPTIONS = ("PENDING", "CONFIRMED_OUTLIER", "CONFIRMED_CONSUMPTION")
STATUS_LABELS = {
    "ALL": "Vse",
    "PENDING": "Ceka na review",
    "CONFIRMED_OUTLIER": "Potvrzeny outlier",
    "CONFIRMED_CONSUMPTION": "Potvrzeny odber",
}
STATUS_ORDER = {
    "PENDING": 0,
    "CONFIRMED_OUTLIER": 1,
    "CONFIRMED_CONSUMPTION": 2,
}
SOURCE_ALL_OPTION = "VSE"
SOURCE_ALL_LABEL = "Vsechny zdroje"
DETECTION_KIND_LABELS = {
    "NORMAL_DELTA": "Standardni interval",
    "GAP_MEAN": "Prumer z gap-fill intervalu",
}


@dataclass(frozen=True)
class OutlierReviewModuleConfig:
    key: str
    label: str
    source_options: tuple[str, ...]
    source_labels: Mapping[str, str]
    load_device_options: Callable[..., list[str]]
    list_reviews: Callable[..., list[dict[str, object]]]
    update_review: Callable[..., dict[str, object]]
    warning: str | None = None


OUTLIER_REVIEW_MODULES: tuple[OutlierReviewModuleConfig, ...] = (
    OutlierReviewModuleConfig(
        key="vodomery",
        label="Vodomery",
        source_options=("VSE", "AREAL", "SCVK"),
        source_labels={
            "VSE": SOURCE_ALL_LABEL,
            "AREAL": "AREAL",
            "SCVK": "SCVK",
        },
        load_device_options=lambda access_token: get_vodomery_devices(access_token, source_filter="VSE", limit=5000),
        list_reviews=list_vodomery_outlier_reviews,
        update_review=update_vodomery_outlier_review,
    ),
    OutlierReviewModuleConfig(
        key="plynomery",
        label="Plynomery",
        source_options=("VSE", "AREAL"),
        source_labels={
            "VSE": SOURCE_ALL_LABEL,
            "AREAL": "AREAL",
        },
        load_device_options=lambda access_token: get_plynomery_devices(access_token, limit=5000),
        list_reviews=list_plynomery_outlier_reviews,
        update_review=update_plynomery_outlier_review,
    ),
    OutlierReviewModuleConfig(
        key="kalorimetry",
        label="Kalorimetry",
        source_options=("VSE", "AREAL"),
        source_labels={
            "VSE": SOURCE_ALL_LABEL,
            "AREAL": "AREAL",
        },
        load_device_options=lambda access_token: get_kalorimetry_devices(access_token, limit=5000),
        list_reviews=list_kalorimetry_outlier_reviews,
        update_review=update_kalorimetry_outlier_review,
    ),
)
OUTLIER_REVIEW_MODULE_MAP = {config.key: config for config in OUTLIER_REVIEW_MODULES}
OUTLIER_REVIEW_MODULE_OPTIONS = ("ALL",) + tuple(config.key for config in OUTLIER_REVIEW_MODULES)
OUTLIER_REVIEW_MODULE_LABELS = {
    "ALL": "Vsechny moduly",
    **{config.key: config.label for config in OUTLIER_REVIEW_MODULES},
}


def get_outlier_review_module_config(module_key: str) -> OutlierReviewModuleConfig:
    try:
        return OUTLIER_REVIEW_MODULE_MAP[module_key]
    except KeyError as exc:
        raise KeyError(f"Neznamy outlier review modul: {module_key}") from exc


def get_selected_outlier_review_module_keys(
    selected_module: str,
    selected_device_module: str | None = None,
) -> tuple[str, ...]:
    if selected_device_module:
        if selected_device_module not in OUTLIER_REVIEW_MODULE_MAP:
            return ()
        return (selected_device_module,)
    if selected_module == "ALL":
        return tuple(config.key for config in OUTLIER_REVIEW_MODULES)
    if selected_module in OUTLIER_REVIEW_MODULE_MAP:
        return (selected_module,)
    return ()


def get_outlier_review_source_options(module_keys: Iterable[str] | None = None) -> tuple[str, ...]:
    selected_keys = set(module_keys or (config.key for config in OUTLIER_REVIEW_MODULES))
    resolved_options: list[str] = []
    for config in OUTLIER_REVIEW_MODULES:
        if config.key not in selected_keys:
            continue
        for option in config.source_options:
            if option not in resolved_options:
                resolved_options.append(option)
    return tuple(resolved_options)


def get_outlier_review_source_label(source_key: str) -> str:
    if source_key == SOURCE_ALL_OPTION:
        return SOURCE_ALL_LABEL
    for config in OUTLIER_REVIEW_MODULES:
        label = config.source_labels.get(source_key)
        if label:
            return label
    return source_key


def resolve_outlier_review_source_filter(selected_source: str, module_key: str) -> str | None:
    config = get_outlier_review_module_config(module_key)
    resolved_source = selected_source or SOURCE_ALL_OPTION
    if resolved_source in config.source_options:
        return resolved_source
    if resolved_source == SOURCE_ALL_OPTION and SOURCE_ALL_OPTION in config.source_options:
        return SOURCE_ALL_OPTION
    return None


def parse_outlier_review_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    return None


def format_outlier_review_timestamp(value: object) -> str:
    parsed = parse_outlier_review_datetime(value)
    if parsed is not None:
        return parsed.strftime("%d.%m.%Y %H:%M")
    if value is None:
        return "-"
    return str(value)


def format_outlier_review_number(value: object, decimals: int = 3) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):,.{decimals}f}".replace(",", " ").replace(".", ",")
    except (TypeError, ValueError):
        return str(value)


def normalize_outlier_review_row(module_key: str, row: Mapping[str, object]) -> dict[str, object]:
    config = get_outlier_review_module_config(module_key)
    normalized = dict(row)
    normalized["module_key"] = config.key
    normalized["module_label"] = config.label
    normalized["_parsed_date"] = parse_outlier_review_datetime(row.get("date"))
    return normalized


def merge_outlier_review_rows(rows: Iterable[Mapping[str, object]], *, limit: int) -> list[dict[str, object]]:
    normalized_rows = [dict(row) for row in rows]
    normalized_rows.sort(
        key=lambda row: (
            STATUS_ORDER.get(str(row.get("review_status") or ""), 99),
            -(
                cast_datetime.timestamp()
                if (cast_datetime := parse_outlier_review_datetime(row.get("_parsed_date") or row.get("date"))) is not None
                else float("inf")
            ),
            str(row.get("module_key") or ""),
            str(row.get("identifikace") or ""),
        )
    )

    if limit >= 0:
        normalized_rows = normalized_rows[:limit]

    merged_rows: list[dict[str, object]] = []
    for row in normalized_rows:
        merged_rows.append({key: value for key, value in row.items() if key != "_parsed_date"})
    return merged_rows


def build_outlier_review_device_options(device_options_by_module: Mapping[str, Iterable[str]]) -> list[tuple[str, str]]:
    resolved_options: list[tuple[str, str]] = [("", "")]
    for config in OUTLIER_REVIEW_MODULES:
        module_devices = sorted({str(item) for item in device_options_by_module.get(config.key, ()) if str(item)})
        resolved_options.extend((config.key, identifikace) for identifikace in module_devices)
    return resolved_options


def format_outlier_review_device_option(option: tuple[str, str]) -> str:
    module_key, identifikace = option
    if not module_key or not identifikace:
        return "Vsechna zarizeni"
    return f"{OUTLIER_REVIEW_MODULE_LABELS.get(module_key, module_key)}: {identifikace}"


def get_outlier_review_warnings(module_keys: Iterable[str]) -> tuple[str, ...]:
    warnings: list[str] = []
    for module_key in module_keys:
        warning = get_outlier_review_module_config(module_key).warning
        if warning and warning not in warnings:
            warnings.append(warning)
    return tuple(warnings)
