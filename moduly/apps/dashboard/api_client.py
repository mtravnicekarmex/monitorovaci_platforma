from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import requests
from decouple import config


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_API_START_COMMAND = "powershell -ExecutionPolicy Bypass -File scripts\\start_api.ps1"


class DashboardApiError(RuntimeError):
    """Raised when the dashboard cannot complete an API request."""


@dataclass(frozen=True)
class DashboardSessionPayload:
    access_token: str
    expires_at: str
    user: dict[str, object]


def _api_base_url() -> str:
    base_url = config("DASHBOARD_API_BASE_URL", default="http://127.0.0.1:8000").strip().rstrip("/")
    if not base_url:
        raise DashboardApiError("DASHBOARD_API_BASE_URL neni nastaveno.")
    return base_url


def _build_url(path: str) -> str:
    return f"{_api_base_url()}{path}"


def _api_unavailable_message(detail: str) -> str:
    return (
        f"Dashboard API neni dostupne na {_api_base_url()}. "
        f"Spust `{DEFAULT_API_START_COMMAND}` nebo nastav `DASHBOARD_API_BASE_URL` na bezici API. "
        f"Puvodni chyba: {detail}"
    )


def _headers(access_token: str | None = None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def _request(
    method: str,
    path: str,
    *,
    access_token: str | None = None,
    json_payload: dict[str, object] | None = None,
    query_params: dict[str, object] | None = None,
    params: dict[str, object] | None = None,
) -> requests.Response:
    resolved_query_params: dict[str, object] | None
    if query_params is None:
        resolved_query_params = params
    elif params is None:
        resolved_query_params = query_params
    else:
        resolved_query_params = {**params, **query_params}

    try:
        response = requests.request(
            method=method,
            url=_build_url(path),
            headers=_headers(access_token),
            json=json_payload,
            params=resolved_query_params,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise DashboardApiError(_api_unavailable_message(str(exc))) from exc

    if 200 <= response.status_code < 300:
        return response

    detail = None
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        detail = payload.get("detail")
    if not detail:
        detail = response.text.strip() or f"HTTP {response.status_code}"

    raise DashboardApiError(str(detail))


def any_dashboard_users_exist() -> bool:
    response = _request("GET", "/api/v1/auth/users-exist")
    payload = response.json()
    return bool(payload.get("users_exist"))


def login(username: str, password: str) -> DashboardSessionPayload:
    response = _request(
        "POST",
        "/api/v1/auth/login",
        json_payload={
            "username": username,
            "password": password,
        },
    )
    payload = response.json()
    return DashboardSessionPayload(
        access_token=str(payload["access_token"]),
        expires_at=str(payload["expires_at"]),
        user=dict(payload["user"]),
    )


def get_me(access_token: str) -> dict[str, object]:
    response = _request("GET", "/api/v1/auth/me", access_token=access_token)
    return dict(response.json())


def update_my_email(access_token: str, email: str | None) -> dict[str, object]:
    response = _request(
        "PATCH",
        "/api/v1/auth/me/email",
        access_token=access_token,
        json_payload={"email": email},
    )
    return dict(response.json())


def change_my_password(access_token: str, current_password: str, new_password: str) -> None:
    _request(
        "POST",
        "/api/v1/auth/me/password",
        access_token=access_token,
        json_payload={
            "current_password": current_password,
            "new_password": new_password,
        },
    )


def logout(access_token: str) -> None:
    _request("POST", "/api/v1/auth/logout", access_token=access_token)


def get_admin_device_options(access_token: str) -> list[str]:
    response = _request(
        "GET",
        "/api/v1/admin/device-options",
        access_token=access_token,
    )
    payload = response.json()
    return [str(item) for item in payload.get("devices", [])]


def list_admin_users(access_token: str) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/admin/users",
        access_token=access_token,
    )
    payload = response.json()
    return [dict(item) for item in payload.get("users", [])]


def create_admin_user(access_token: str, payload: dict[str, object]) -> dict[str, object]:
    response = _request(
        "POST",
        "/api/v1/admin/users",
        access_token=access_token,
        json_payload=payload,
    )
    return dict(response.json())


def update_admin_user(access_token: str, username: str, payload: dict[str, object]) -> dict[str, object]:
    response = _request(
        "PATCH",
        f"/api/v1/admin/users/{username}",
        access_token=access_token,
        json_payload=payload,
    )
    return dict(response.json())


def delete_admin_user(access_token: str, username: str) -> None:
    _request(
        "DELETE",
        f"/api/v1/admin/users/{username}",
        access_token=access_token,
    )


def get_scheduler_health(access_token: str) -> dict[str, object]:
    response = _request(
        "GET",
        "/health/scheduler",
        access_token=access_token,
    )
    return dict(response.json())


def get_scheduler_log(access_token: str, *, lines: int = 300) -> dict[str, object]:
    response = _request(
        "GET",
        "/health/scheduler/log",
        access_token=access_token,
        params={"lines": int(lines)},
    )
    return dict(response.json())


def run_scheduler_job_once(access_token: str, job_id: str) -> dict[str, object]:
    response = _request(
        "POST",
        f"/health/scheduler/jobs/{job_id}/run",
        access_token=access_token,
    )
    return dict(response.json())


def preview_web_search_hits(access_token: str, payload: dict[str, object]) -> dict[str, object]:
    response = _request(
        "POST",
        "/api/v1/web-search/preview",
        access_token=access_token,
        json_payload=payload,
    )
    return dict(response.json())


def list_web_search_monitors(access_token: str) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/web-search/monitors",
        access_token=access_token,
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def create_web_search_monitor(access_token: str, payload: dict[str, object]) -> dict[str, object]:
    response = _request(
        "POST",
        "/api/v1/web-search/monitors",
        access_token=access_token,
        json_payload=payload,
    )
    return dict(response.json())


def update_web_search_monitor(access_token: str, monitor_id: int, payload: dict[str, object]) -> dict[str, object]:
    response = _request(
        "PATCH",
        f"/api/v1/web-search/monitors/{monitor_id}",
        access_token=access_token,
        json_payload=payload,
    )
    return dict(response.json())


def delete_web_search_monitor(access_token: str, monitor_id: int) -> None:
    _request(
        "DELETE",
        f"/api/v1/web-search/monitors/{monitor_id}",
        access_token=access_token,
    )


def list_web_search_results(access_token: str, limit: int = 200) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/web-search/results",
        access_token=access_token,
        query_params={"limit": limit},
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def get_manometry_devices(access_token: str, limit: int = 500) -> list[str]:
    response = _request(
        "GET",
        "/api/v1/manometry/devices",
        access_token=access_token,
        query_params={"limit": limit},
    )
    payload = response.json()
    return [str(item) for item in payload.get("devices", [])]


def get_manometry_measurement_series(
    access_token: str,
    *,
    identifikace: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/manometry/measurement-series",
        access_token=access_token,
        query_params={
            "identifikace": identifikace,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def get_manometry_device_detail(
    access_token: str,
    *,
    identifikace: str,
) -> dict[str, object] | None:
    response = _request(
        "GET",
        "/api/v1/manometry/device-detail",
        access_token=access_token,
        query_params={"identifikace": identifikace},
    )
    payload = response.json()
    if not payload.get("found"):
        return None
    device = payload.get("device")
    return dict(device) if isinstance(device, dict) else None


def get_vodomery_devices(access_token: str, source_filter: str = "VSE", limit: int = 500) -> list[str]:
    response = _request(
        "GET",
        "/api/v1/vodomery/devices",
        access_token=access_token,
        query_params={
            "source": source_filter,
            "limit": limit,
        },
    )
    payload = response.json()
    return [str(item) for item in payload.get("devices", [])]


def get_vodomery_billing_options(access_token: str) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/vodomery/billing-options",
        access_token=access_token,
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def get_vodomery_billing_period(
    access_token: str,
    *,
    billing_ident: str,
    start_date: str,
    end_date: str,
) -> dict[str, object]:
    response = _request(
        "GET",
        "/api/v1/vodomery/billing-period",
        access_token=access_token,
        query_params={
            "billing_ident": billing_ident,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    return dict(response.json())


def get_vodomery_overview_metrics(
    access_token: str,
    *,
    start_date: str,
    end_date: str,
    source_filter: str = "VSE",
) -> dict[str, int]:
    response = _request(
        "GET",
        "/api/v1/vodomery/overview-metrics",
        access_token=access_token,
        query_params={
            "start_date": start_date,
            "end_date": end_date,
            "source": source_filter,
        },
    )
    payload = response.json()
    return {
        "zarizeni": int(payload.get("zarizeni", 0)),
        "mereni": int(payload.get("mereni", 0)),
        "anomalie": int(payload.get("anomalie", 0)),
        "aktivni_eventy": int(payload.get("aktivni_eventy", 0)),
    }


def get_vodomery_branch_day_overview(
    access_token: str,
    *,
    target_date: str,
) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/vodomery/branch-day-overview",
        access_token=access_token,
        query_params={"target_date": target_date},
    )
    payload = response.json()
    return [dict(item) for item in payload.get("branches", [])]


def get_vodomery_measurement_series(
    access_token: str,
    *,
    identifikace: str,
    start_date: str,
    end_date: str,
    source_filter: str = "VSE",
) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/vodomery/measurement-series",
        access_token=access_token,
        query_params={
            "identifikace": identifikace,
            "start_date": start_date,
            "end_date": end_date,
            "source": source_filter,
        },
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def get_vodomery_prediction_profiles(
    access_token: str,
    *,
    identifikace: str,
) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/vodomery/prediction-profiles",
        access_token=access_token,
        query_params={"identifikace": identifikace},
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def get_vodomery_recent_anomalies(
    access_token: str,
    *,
    start_date: str,
    end_date: str,
    identifikace: str | None = None,
    source_filter: str = "VSE",
    limit: int = 50,
) -> list[dict[str, object]]:
    query_params: dict[str, object] = {
        "start_date": start_date,
        "end_date": end_date,
        "source": source_filter,
        "limit": limit,
    }
    if identifikace:
        query_params["identifikace"] = identifikace
    response = _request(
        "GET",
        "/api/v1/vodomery/recent-anomalies",
        access_token=access_token,
        query_params=query_params,
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def get_vodomery_open_events(
    access_token: str,
    *,
    limit: int = 500,
) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/vodomery/open-events",
        access_token=access_token,
        query_params={"limit": limit},
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def get_vodomery_resolved_events(
    access_token: str,
    *,
    days: int = 7,
    limit: int = 500,
) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/vodomery/resolved-events",
        access_token=access_token,
        query_params={
            "days": days,
            "limit": limit,
        },
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def get_vodomery_event_history(
    access_token: str,
    *,
    identifikace: str,
    limit: int = 20,
) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/vodomery/event-history",
        access_token=access_token,
        query_params={
            "identifikace": identifikace,
            "limit": limit,
        },
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def get_vodomery_device_detail(
    access_token: str,
    *,
    identifikace: str,
) -> dict[str, object] | None:
    response = _request(
        "GET",
        "/api/v1/vodomery/device-detail",
        access_token=access_token,
        query_params={"identifikace": identifikace},
    )
    payload = response.json()
    if not payload.get("found"):
        return None
    device = payload.get("device")
    return dict(device) if isinstance(device, dict) else None


def get_vodomery_expected_zero(access_token: str) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/vodomery/expected-zero",
        access_token=access_token,
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def list_vodomery_outlier_reviews(
    access_token: str,
    *,
    review_status: str | None = "PENDING",
    identifikace: str | None = None,
    source_filter: str = "VSE",
    limit: int = 200,
) -> list[dict[str, object]]:
    query_params: dict[str, object] = {
        "source": source_filter,
        "limit": limit,
    }
    if review_status is not None:
        query_params["review_status"] = review_status
    if identifikace:
        query_params["identifikace"] = identifikace

    response = _request(
        "GET",
        "/api/v1/vodomery/outlier-reviews",
        access_token=access_token,
        query_params=query_params,
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def update_vodomery_outlier_review(
    access_token: str,
    review_id: int,
    payload: dict[str, object],
) -> dict[str, object]:
    response = _request(
        "PATCH",
        f"/api/v1/vodomery/outlier-reviews/{review_id}",
        access_token=access_token,
        json_payload=payload,
    )
    return dict(response.json())


def update_vodomery_expected_zero(access_token: str, identifikace_list: list[str]) -> list[dict[str, object]]:
    response = _request(
        "PUT",
        "/api/v1/vodomery/expected-zero",
        access_token=access_token,
        json_payload={"identifikace_list": identifikace_list},
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def list_vodomery_alert_rules(access_token: str) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/vodomery/alert-rules",
        access_token=access_token,
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def create_vodomery_alert_rule(access_token: str, payload: dict[str, object]) -> dict[str, object]:
    response = _request(
        "POST",
        "/api/v1/vodomery/alert-rules",
        access_token=access_token,
        json_payload=payload,
    )
    return dict(response.json())


def update_vodomery_alert_rule(access_token: str, rule_id: int, payload: dict[str, object]) -> dict[str, object]:
    response = _request(
        "PATCH",
        f"/api/v1/vodomery/alert-rules/{rule_id}",
        access_token=access_token,
        json_payload=payload,
    )
    return dict(response.json())


def delete_vodomery_alert_rule(access_token: str, rule_id: int) -> None:
    _request(
        "DELETE",
        f"/api/v1/vodomery/alert-rules/{rule_id}",
        access_token=access_token,
    )


def get_plynomery_devices(access_token: str, limit: int = 500) -> list[str]:
    response = _request(
        "GET",
        "/api/v1/plynomery/devices",
        access_token=access_token,
        query_params={"limit": limit},
    )
    payload = response.json()
    return [str(item) for item in payload.get("devices", [])]


def get_plynomery_recent_anomalies(
    access_token: str,
    *,
    start_date: str,
    end_date: str,
    identifikace: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    query_params: dict[str, object] = {
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit,
    }
    if identifikace:
        query_params["identifikace"] = identifikace
    response = _request(
        "GET",
        "/api/v1/plynomery/recent-anomalies",
        access_token=access_token,
        query_params=query_params,
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def get_plynomery_open_events(
    access_token: str,
    *,
    limit: int = 500,
) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/plynomery/open-events",
        access_token=access_token,
        query_params={"limit": limit},
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def get_plynomery_resolved_events(
    access_token: str,
    *,
    days: int = 7,
    limit: int = 500,
) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/plynomery/resolved-events",
        access_token=access_token,
        query_params={
            "days": days,
            "limit": limit,
        },
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def get_plynomery_expected_zero(access_token: str) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/plynomery/expected-zero",
        access_token=access_token,
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def list_plynomery_outlier_reviews(
    access_token: str,
    *,
    review_status: str | None = "PENDING",
    identifikace: str | None = None,
    source_filter: str = "VSE",
    limit: int = 200,
) -> list[dict[str, object]]:
    query_params: dict[str, object] = {
        "source": source_filter,
        "limit": limit,
    }
    if review_status is not None:
        query_params["review_status"] = review_status
    if identifikace:
        query_params["identifikace"] = identifikace

    response = _request(
        "GET",
        "/api/v1/plynomery/outlier-reviews",
        access_token=access_token,
        query_params=query_params,
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def update_plynomery_outlier_review(
    access_token: str,
    review_id: int,
    payload: dict[str, object],
) -> dict[str, object]:
    response = _request(
        "PATCH",
        f"/api/v1/plynomery/outlier-reviews/{review_id}",
        access_token=access_token,
        json_payload=payload,
    )
    return dict(response.json())


def update_plynomery_expected_zero(access_token: str, identifikace_list: list[str]) -> list[dict[str, object]]:
    response = _request(
        "PUT",
        "/api/v1/plynomery/expected-zero",
        access_token=access_token,
        json_payload={"identifikace_list": identifikace_list},
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def list_plynomery_alert_rules(access_token: str) -> list[dict[str, object]]:
    response = _request(
        "GET",
        "/api/v1/plynomery/alert-rules",
        access_token=access_token,
    )
    payload = response.json()
    return [dict(item) for item in payload.get("rows", [])]


def create_plynomery_alert_rule(access_token: str, payload: dict[str, object]) -> dict[str, object]:
    response = _request(
        "POST",
        "/api/v1/plynomery/alert-rules",
        access_token=access_token,
        json_payload=payload,
    )
    return dict(response.json())


def update_plynomery_alert_rule(access_token: str, rule_id: int, payload: dict[str, object]) -> dict[str, object]:
    response = _request(
        "PATCH",
        f"/api/v1/plynomery/alert-rules/{rule_id}",
        access_token=access_token,
        json_payload=payload,
    )
    return dict(response.json())


def delete_plynomery_alert_rule(access_token: str, rule_id: int) -> None:
    _request(
        "DELETE",
        f"/api/v1/plynomery/alert-rules/{rule_id}",
        access_token=access_token,
    )
