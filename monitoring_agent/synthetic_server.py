from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any


SCENARIOS = {
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
                "label": "Synthetic quarter-hour job",
                "status": status,
                "last_status": "success",
                "last_run": heartbeat.isoformat(),
                "next_run": (checked_at + timedelta(minutes=15)).isoformat(),
                "success_count_24h": 4 if scheduler_running else 3,
                "failure_count_24h": 0,
                "last_duration_seconds": 0.1,
                "detail": "Synthetic test data.",
            }
        ],
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
