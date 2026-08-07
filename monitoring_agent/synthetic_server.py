from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any


SCENARIOS = {
    "external_redirect",
    "healthy",
    "invalid_schema",
    "readiness_unavailable",
    "scheduler_stopped",
    "unauthorized",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _system_scheduler_payload(scenario: str) -> dict[str, object]:
    checked_at = _now()
    scheduler_running = scenario != "scheduler_stopped"
    heartbeat = checked_at if scheduler_running else checked_at - timedelta(minutes=20)
    status = "ok" if scheduler_running else "error"
    return {
        "status": status,
        "checked_at": checked_at.isoformat(),
        "scheduler_running": scheduler_running,
        "last_heartbeat": heartbeat.isoformat(),
        "heartbeat_age_seconds": 0.0 if scheduler_running else 1200.0,
        "heartbeat_ttl_seconds": 300,
        "total_success_count_24h": 4 if scheduler_running else 3,
        "total_failure_count_24h": 0,
        "jobs": [
            {
                "job_id": "quarter_hour_job",
                "status": status,
                "last_status": "success",
                "last_run": heartbeat.isoformat(),
                "next_run": (checked_at + timedelta(minutes=15)).isoformat(),
                "success_count_24h": 4 if scheduler_running else 3,
                "failure_count_24h": 0,
                "last_duration_seconds": 0.1,
            }
        ],
    }


def _system_runtime_payload(*, invalid_schema: bool = False) -> dict[str, object]:
    checked_at = _now()
    boot_time = checked_at - timedelta(hours=1)
    listener = {
        "key": "api",
        "status": "ok",
        "expected": True,
        "present": True,
        "local_port": 8000,
    }
    payload: dict[str, object] = {
        "status": "ok",
        "checked_at": checked_at.isoformat(),
        "boot": {
            "status": "ok",
            "boot_time": boot_time.isoformat(),
        },
        "startup_task": {
            "task_name": "API_dashboard_caddy",
            "status": "ok",
            "last_run_time": boot_time.isoformat(),
            "last_task_result": 0,
        },
        "expected_listeners": [listener],
        "temporary_listeners": [
            {
                "key": "temporary_api",
                "status": "ok",
                "expected": False,
                "present": False,
                "local_port": 8010,
            }
        ],
    }
    if invalid_schema:
        payload["unexpected"] = True
    return payload


def _scheduler_detail_payload() -> dict[str, object]:
    checked_at = _now()
    return {
        "status": "ok",
        "scheduler_running": True,
        "jobs": [
            {
                "id": "quarter_hour_job",
                "is_scheduled": True,
                "last_run": checked_at.isoformat(),
                "last_status": "success",
                "last_duration_seconds": 0.1,
                "next_run": (checked_at + timedelta(minutes=15)).isoformat(),
                "failure_rate_24h": 0.0,
                "avg_duration_24h": 0.1,
            }
        ],
        "schedule": [
            {
                "job_id": "quarter_hour_job",
                "scheduled_at": (checked_at + timedelta(minutes=15)).isoformat(),
            }
        ],
        "checked_at": checked_at.isoformat(),
    }


def _system_database_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "checked_at": _now().isoformat(),
        "postgres": {
            "status": "ok",
            "connected": True,
            "latency_ms": 1.5,
            "transaction_read_only": False,
        },
        "expected_schemas": [
            {"schema_name": "monitoring", "status": "ok", "present": True}
        ],
    }


def _system_proxy_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "checked_at": _now().isoformat(),
        "routes": [
            {
                "key": "https_dashboard",
                "status": "ok",
                "expected_status_code": 200,
                "actual_status_code": 200,
            }
        ],
        "headers": [
            {
                "key": "strict_transport_security",
                "status": "ok",
                "expected": "present",
                "present": True,
            }
        ],
    }


def _system_smartfuelpass_payload() -> dict[str, object]:
    checked_at = _now()
    job = {
        "job_id": "sync_charge_sessions_to_db",
        "status": "ok",
        "last_status": "success",
        "last_run": checked_at.isoformat(),
        "success_count_24h": 1,
        "failure_count_24h": 0,
        "last_duration_seconds": 1.0,
    }
    weekly_job = dict(job)
    weekly_job["job_id"] = "smartfuelpass_weekly_report_job"
    return {
        "status": "ok",
        "checked_at": checked_at.isoformat(),
        "table": {
            "status": "ok",
            "table_present": True,
            "missing_ended_at_utc_count": 0,
            "last_imported_at": checked_at.isoformat(),
            "last_import_age_seconds": 0.0,
        },
        "sync_job": job,
        "weekly_report_job": weekly_job,
    }


class SyntheticHealthServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], *, scenario: str) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"unsupported scenario: {scenario}")
        self.scenario = scenario
        super().__init__(server_address, SyntheticHealthHandler)


class SyntheticHealthHandler(BaseHTTPRequestHandler):
    server: SyntheticHealthServer

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        if self.path == "/":
            if self.headers.get("Authorization"):
                self._send(400, {"status": "authorization_header_forbidden"})
            elif self.server.scenario == "external_redirect":
                self.send_response(302)
                self.send_header("Location", "/redirect-target")
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif self.server.scenario == "invalid_schema":
                self._send(200, {"status": "not_html"})
            else:
                self._send_html(200, b"<!doctype html><title>synthetic</title>")
            return
        if self.path == "/redirect-target":
            self._send_html(200, b"<!doctype html><title>redirected</title>")
            return
        if self.server.scenario == "unauthorized":
            self._send(401, {"status": "unauthorized"})
            return
        if self.path == "/api/v1/monitoring/health/live":
            self._send(
                200,
                (
                    {"status": "ok", "unexpected": True}
                    if self.server.scenario == "invalid_schema"
                    else {"status": "ok"}
                ),
            )
            return
        if self.path == "/api/v1/monitoring/health/ready":
            unavailable = self.server.scenario == "readiness_unavailable"
            self._send(
                503 if unavailable else 200,
                {"status": "unavailable" if unavailable else "ready"},
            )
            return
        if self.path == "/api/v1/monitoring/health/system/scheduler":
            self._send(200, _system_scheduler_payload(self.server.scenario))
            return
        if self.path == "/api/v1/monitoring/health/scheduler":
            self._send(200, _scheduler_detail_payload())
            return
        if self.path == "/api/v1/monitoring/health/system/runtime":
            self._send(
                200,
                _system_runtime_payload(
                    invalid_schema=self.server.scenario == "invalid_schema"
                ),
            )
            return
        if self.path == "/api/v1/monitoring/health/system/database":
            self._send(200, _system_database_payload())
            return
        if self.path == "/api/v1/monitoring/health/system/proxy":
            self._send(200, _system_proxy_payload())
            return
        if self.path == "/api/v1/monitoring/health/system/smartfuelpass":
            self._send(200, _system_smartfuelpass_payload())
            return
        self._send(404, {"status": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        self._send(405, {"status": "method_not_allowed"})

    def log_message(self, format: str, *args: Any) -> None:
        del format, args

    def _send(self, status_code: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode(
            "utf-8"
        )
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status_code: int, body: bytes) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8020,
    scenario: str = "healthy",
) -> SyntheticHealthServer:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("synthetic server may bind only to loopback")
    return SyntheticHealthServer((host, port), scenario=scenario)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve synthetic scheduler health responses on loopback only."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="healthy")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    server = create_server(host=args.host, port=args.port, scenario=args.scenario)
    print(
        json.dumps(
            {
                "event": "synthetic_server_started",
                "host": "loopback",
                "port": server.server_port,
                "scenario": args.scenario,
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
