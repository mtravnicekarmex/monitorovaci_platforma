from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from .client import Observation

if os.name == "nt":
    import msvcrt
else:
    import fcntl


LIFECYCLE_CONTRACT_VERSION = 1
WRITER_LOCK_FILE_NAME = "observer_writer.lock"
LIFECYCLE_EVENT_REASONS = {
    "process_started": {"observer_started"},
    "process_stopped": {
        "keyboard_interrupt",
        "observer_error",
        "once_completed",
    },
}


class StateWriterLockError(RuntimeError):
    """The agent-owned state cannot safely accept another writer."""


class StateWriterLock:
    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir.resolve()
        self._lock_path = self._state_dir / WRITER_LOCK_FILE_NAME
        self._file_descriptor: int | None = None

    def __enter__(self) -> StateWriterLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()

    def acquire(self) -> None:
        if self._file_descriptor is not None:
            raise StateWriterLockError("state writer lock is already acquired")
        file_descriptor: int | None = None
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            file_descriptor = os.open(
                self._lock_path,
                os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0),
                0o600,
            )
            if os.fstat(file_descriptor).st_size == 0:
                os.write(file_descriptor, b"\0")
                os.fsync(file_descriptor)
            os.lseek(file_descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                msvcrt.locking(file_descriptor, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if file_descriptor is not None:
                os.close(file_descriptor)
            raise StateWriterLockError("state writer lock is unavailable") from exc
        self._file_descriptor = file_descriptor

    def release(self) -> None:
        file_descriptor = self._file_descriptor
        if file_descriptor is None:
            return
        self._file_descriptor = None
        release_error: OSError | None = None
        try:
            os.lseek(file_descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                msvcrt.locking(file_descriptor, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file_descriptor, fcntl.LOCK_UN)
        except OSError as exc:
            release_error = exc
        finally:
            os.close(file_descriptor)
        if release_error is not None:
            raise StateWriterLockError(
                "state writer lock could not be released"
            ) from release_error


class ObserverStore:
    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir.resolve()
        self._observations_path = self._state_dir / "observations.jsonl"
        self._heartbeat_path = self._state_dir / "observer_heartbeat.json"
        self._lifecycle_path = self._state_dir / "observer_lifecycle.jsonl"

    @property
    def observations_path(self) -> Path:
        return self._observations_path

    @property
    def heartbeat_path(self) -> Path:
        return self._heartbeat_path

    @property
    def lifecycle_path(self) -> Path:
        return self._lifecycle_path

    def writer_lock(self) -> StateWriterLock:
        return StateWriterLock(self._state_dir)

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
        run_id: str,
        status: str,
        cycle_id: str,
        cycle_started_at: str,
        cycle_finished_at: str | None = None,
        observation_count: int = 0,
        transport_failure_count: int = 0,
    ) -> None:
        if status not in {"polling", "healthy", "degraded"}:
            raise ValueError("invalid observer heartbeat status")
        if (
            not observer_instance_id.strip()
            or not run_id.strip()
            or not cycle_id.strip()
        ):
            raise ValueError("observer heartbeat identity is required")
        self._state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "observer_instance_id": observer_instance_id,
            "run_id": run_id,
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

    def append_lifecycle(
        self,
        *,
        observer_instance_id: str,
        run_id: str,
        event: str,
        reason: str,
    ) -> None:
        if event not in LIFECYCLE_EVENT_REASONS:
            raise ValueError("invalid observer lifecycle event")
        if reason not in LIFECYCLE_EVENT_REASONS[event]:
            raise ValueError("invalid observer lifecycle reason")
        if not observer_instance_id.strip() or not run_id.strip():
            raise ValueError("observer lifecycle identity is required")
        self._state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "lifecycle_contract_version": LIFECYCLE_CONTRACT_VERSION,
            "event_id": str(uuid4()),
            "observer_instance_id": observer_instance_id.strip(),
            "run_id": run_id.strip(),
            "process_id": os.getpid(),
            "event": event,
            "reason": reason,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        with self._lifecycle_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
