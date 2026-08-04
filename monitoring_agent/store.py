from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from .client import Observation


class ObserverStore:
    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir.resolve()
        self._observations_path = self._state_dir / "observations.jsonl"
        self._heartbeat_path = self._state_dir / "observer_heartbeat.json"

    @property
    def observations_path(self) -> Path:
        return self._observations_path

    @property
    def heartbeat_path(self) -> Path:
        return self._heartbeat_path

    def append(self, observation: Observation) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(
            observation.to_dict(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        with self._observations_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.write("\n")

    def write_heartbeat(
        self,
        *,
        observer_instance_id: str,
        status: str,
        cycle_id: str,
        cycle_started_at: str,
        cycle_finished_at: str | None = None,
        observation_count: int = 0,
        transport_failure_count: int = 0,
    ) -> None:
        if status not in {"polling", "healthy", "degraded"}:
            raise ValueError("invalid observer heartbeat status")
        self._state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "observer_instance_id": observer_instance_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "process_id": os.getpid(),
            "status": status,
            "cycle_id": cycle_id,
            "cycle_started_at": cycle_started_at,
            "cycle_finished_at": cycle_finished_at,
            "observation_count": observation_count,
            "transport_failure_count": transport_failure_count,
        }
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix="observer-heartbeat-",
            suffix=".tmp",
            dir=self._state_dir,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(
                    payload,
                    handle,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary_path.replace(self._heartbeat_path)
        finally:
            temporary_path.unlink(missing_ok=True)
