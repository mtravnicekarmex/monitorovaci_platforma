from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from local_monitoring_agents.database_availability import (
    load_database_availability_local_agent_facade_snapshot,
)
from local_monitoring_agents.scheduler_metrics import (
    load_scheduler_metrics_local_agent_facade_snapshot,
)
from services.api.services.monitoring_facade import (
    project_database_availability_local_agent,
    project_scheduler_metrics_local_agent,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export sanitized local monitoring facade aggregates as file-only "
            "orchestrator pilot inputs. This script does not read .env, poll "
            "endpoints, send email, mutate application state, or control tasks."
        )
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=(
            PROJECT_ROOT
            / "artifacts"
            / "monitoring"
            / "orchestrator"
            / f"{date.today().isoformat()}-file-only-pilot"
        ),
    )
    parser.add_argument(
        "--remote-audit-file",
        type=Path,
        help=(
            "Optional sanitized remote monitoring-agent --audit-state JSON file. "
            "When supplied, the script writes a full three-agent registry."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifact_dir = args.artifact_dir.resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    db_file = artifact_dir / "database-availability.json"
    scheduler_file = artifact_dir / "scheduler-metrics.json"
    _write_json(
        db_file,
        _model_to_dict(
            project_database_availability_local_agent(
                load_database_availability_local_agent_facade_snapshot()
            )
        ),
    )
    _write_json(
        scheduler_file,
        _model_to_dict(
            project_scheduler_metrics_local_agent(
                load_scheduler_metrics_local_agent_facade_snapshot()
            )
        ),
    )

    registry_agents = [
        _registry_agent(
            agent_key="database_availability",
            agent_kind="local_facade_agent",
            location="main_workstation",
            payload_kind="local_agent_facade_v1",
            source_file=db_file.name,
            contract_version_min=1,
            contract_version_max=1,
            stale_after_seconds=300,
        ),
        _registry_agent(
            agent_key="scheduler_metrics",
            agent_kind="local_facade_agent",
            location="main_workstation",
            payload_kind="local_agent_facade_v1",
            source_file=scheduler_file.name,
            contract_version_min=1,
            contract_version_max=1,
            stale_after_seconds=300,
        ),
    ]

    remote_audit_written = False
    if args.remote_audit_file is not None:
        remote_source = args.remote_audit_file.resolve()
        _reject_env_path(remote_source)
        remote_payload = json.loads(remote_source.read_text(encoding="utf-8"))
        remote_file = artifact_dir / "remote-audit.json"
        _write_json(remote_file, remote_payload)
        registry_agents.insert(
            0,
            _registry_agent(
                agent_key="external_health",
                agent_kind="remote_observer",
                location="supervision_center",
                payload_kind="remote_agent_audit_v8",
                source_file=remote_file.name,
                contract_version_min=8,
                contract_version_max=8,
                stale_after_seconds=300,
            ),
        )
        remote_audit_written = True
        registry_file = artifact_dir / "orchestrator-registry.json"
    else:
        registry_file = artifact_dir / "orchestrator-registry-local-only.json"

    _write_json(
        registry_file,
        {
            "agents": registry_agents,
            "contract_version": 1,
            "event": "monitoring_orchestrator_registry",
            "mode": "file_only",
        },
    )

    print(
        json.dumps(
            {
                "artifact_dir": str(artifact_dir),
                "database_availability_file": str(db_file),
                "event": "monitoring_orchestrator_local_inputs_exported",
                "registry_file": str(registry_file),
                "remote_audit_included": remote_audit_written,
                "scheduler_metrics_file": str(scheduler_file),
                "status": (
                    "ready_for_full_pilot"
                    if remote_audit_written
                    else "local_preflight_only_remote_audit_required"
                ),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


def _registry_agent(
    *,
    agent_key: str,
    agent_kind: str,
    location: str,
    payload_kind: str,
    source_file: str,
    contract_version_min: int,
    contract_version_max: int,
    stale_after_seconds: int,
) -> dict[str, object]:
    return {
        "agent_key": agent_key,
        "agent_kind": agent_kind,
        "contract_version_max": contract_version_max,
        "contract_version_min": contract_version_min,
        "enabled": True,
        "location": location,
        "payload_kind": payload_kind,
        "source_file": source_file,
        "stale_after_seconds": stale_after_seconds,
        "status_mapping_version": 1,
    }


def _model_to_dict(model) -> dict[str, object]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return json.loads(model.json())


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _reject_env_path(path: Path) -> None:
    if any(part.lower() == ".env" for part in path.parts):
        raise ValueError("remote audit file must not be an .env path")
    if path.name.lower().startswith(".env"):
        raise ValueError("remote audit file must not be an .env path")


if __name__ == "__main__":
    raise SystemExit(main())
