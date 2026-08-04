from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path

from .client import APPROVED_ENDPOINTS, validate_base_url


ENV_CONTRACT_VERSION = 1
ENV_KEYS = {
    "MONITORING_AGENT_ENV_VERSION",
    "MONITORING_AGENT_MODE",
    "MONITORING_AGENT_INSTANCE_ID",
    "MONITORING_AGENT_BASE_URL",
    "MONITORING_AGENT_STATE_DIR",
    "MONITORING_AGENT_TIMEOUT_SECONDS",
    "MONITORING_AGENT_MAX_ATTEMPTS",
    "MONITORING_AGENT_RETRY_BACKOFF_SECONDS",
    "MONITORING_AGENT_POLL_INTERVAL_SECONDS",
    "MONITORING_AGENT_POLL_JITTER_SECONDS",
    "MONITORING_AGENT_ENDPOINT_KEYS",
    "MONITORING_AGENT_BEARER_TOKEN",
}
ENV_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True)
class RuntimeSettings:
    env_contract_version: int
    mode: str
    instance_id: str
    base_url: str
    state_dir: Path
    timeout_seconds: float
    max_attempts: int
    retry_backoff_seconds: float
    poll_interval_seconds: float
    poll_jitter_seconds: float
    endpoint_keys: tuple[str, ...]
    bearer_credential: str = field(repr=False)

    @classmethod
    def load(cls, path: Path) -> RuntimeSettings:
        env_path = path.resolve()
        values = _read_strict_env(env_path)
        actual_keys = set(values)
        if actual_keys != ENV_KEYS:
            raise ValueError(
                "environment schema mismatch: "
                f"missing={sorted(ENV_KEYS - actual_keys)!r}, "
                f"unexpected={sorted(actual_keys - ENV_KEYS)!r}"
            )

        env_version = _integer(
            values["MONITORING_AGENT_ENV_VERSION"],
            name="MONITORING_AGENT_ENV_VERSION",
        )
        if env_version != ENV_CONTRACT_VERSION:
            raise ValueError(f"unsupported environment contract: {env_version!r}")
        if values["MONITORING_AGENT_MODE"] != "test":
            raise ValueError("the observer supports only test mode")

        instance_id = values["MONITORING_AGENT_INSTANCE_ID"].strip()
        if not instance_id:
            raise ValueError("MONITORING_AGENT_INSTANCE_ID must not be empty")

        base_url = validate_base_url(values["MONITORING_AGENT_BASE_URL"])
        if base_url.startswith("https://example.invalid"):
            raise ValueError("MONITORING_AGENT_BASE_URL still contains a placeholder")

        raw_state_dir = values["MONITORING_AGENT_STATE_DIR"].strip()
        if not raw_state_dir:
            raise ValueError("MONITORING_AGENT_STATE_DIR must not be empty")
        state_dir = Path(raw_state_dir)
        if not state_dir.is_absolute():
            state_dir = env_path.parent / state_dir
        state_dir = state_dir.resolve()
        if state_dir == env_path.parent or state_dir.is_relative_to(env_path.parent):
            raise ValueError(
                "MONITORING_AGENT_STATE_DIR must be outside the code/config directory"
            )

        timeout_seconds = _positive_number(
            values["MONITORING_AGENT_TIMEOUT_SECONDS"],
            name="MONITORING_AGENT_TIMEOUT_SECONDS",
        )
        max_attempts = _integer(
            values["MONITORING_AGENT_MAX_ATTEMPTS"],
            name="MONITORING_AGENT_MAX_ATTEMPTS",
        )
        if max_attempts < 1 or max_attempts > 5:
            raise ValueError("MONITORING_AGENT_MAX_ATTEMPTS must be between 1 and 5")
        retry_backoff_seconds = _non_negative_number(
            values["MONITORING_AGENT_RETRY_BACKOFF_SECONDS"],
            name="MONITORING_AGENT_RETRY_BACKOFF_SECONDS",
        )
        poll_interval_seconds = _positive_number(
            values["MONITORING_AGENT_POLL_INTERVAL_SECONDS"],
            name="MONITORING_AGENT_POLL_INTERVAL_SECONDS",
        )
        poll_jitter_seconds = _non_negative_number(
            values["MONITORING_AGENT_POLL_JITTER_SECONDS"],
            name="MONITORING_AGENT_POLL_JITTER_SECONDS",
        )
        if poll_jitter_seconds > poll_interval_seconds:
            raise ValueError(
                "MONITORING_AGENT_POLL_JITTER_SECONDS must not exceed the poll interval"
            )

        endpoint_keys = tuple(
            item.strip()
            for item in values["MONITORING_AGENT_ENDPOINT_KEYS"].split(",")
            if item.strip()
        )
        if not endpoint_keys:
            raise ValueError("MONITORING_AGENT_ENDPOINT_KEYS must not be empty")
        if len(endpoint_keys) != len(set(endpoint_keys)):
            raise ValueError("MONITORING_AGENT_ENDPOINT_KEYS contains duplicates")
        unknown_endpoints = set(endpoint_keys) - set(APPROVED_ENDPOINTS)
        if unknown_endpoints:
            raise ValueError(
                "MONITORING_AGENT_ENDPOINT_KEYS contains unapproved values: "
                f"{sorted(unknown_endpoints)!r}"
            )

        bearer_credential = values["MONITORING_AGENT_BEARER_TOKEN"]
        if (
            len(bearer_credential) < 32
            or any(character.isspace() for character in bearer_credential)
            or "change-me" in bearer_credential.lower()
        ):
            raise ValueError("MONITORING_AGENT_BEARER_TOKEN has an invalid format")

        return cls(
            env_contract_version=ENV_CONTRACT_VERSION,
            mode="test",
            instance_id=instance_id,
            base_url=base_url,
            state_dir=state_dir,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
            poll_interval_seconds=poll_interval_seconds,
            poll_jitter_seconds=poll_jitter_seconds,
            endpoint_keys=endpoint_keys,
            bearer_credential=bearer_credential,
        )

    def safe_summary(self) -> dict[str, object]:
        return {
            "endpoint_count": len(self.endpoint_keys),
            "env_contract_version": self.env_contract_version,
            "mode": self.mode,
        }


def _read_strict_env(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ValueError("environment file could not be read") from exc

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ValueError(f"environment line {line_number} is invalid")
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        if not ENV_KEY_PATTERN.fullmatch(key):
            raise ValueError(f"environment line {line_number} has an invalid key")
        if key in values:
            raise ValueError(f"environment key is duplicated: {key}")
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _integer(value: str, *, name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _positive_number(value: str, *, name: str) -> float:
    resolved = _number(value, name=name)
    if resolved <= 0:
        raise ValueError(f"{name} must be positive")
    return resolved


def _non_negative_number(value: str, *, name: str) -> float:
    resolved = _number(value, name=name)
    if resolved < 0:
        raise ValueError(f"{name} must not be negative")
    return resolved


def _number(value: str, *, name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
