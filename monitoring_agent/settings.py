from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path

from .client import (
    CONTRACT_ENDPOINT_SET_VERSIONS,
    ENDPOINT_SETS,
    validate_base_url,
    validate_external_web_url,
)


ENV_CONTRACT_VERSION = 3
LEGACY_ENV_CONTRACT_VERSION = 1
STATE_ENV_CONTRACT_VERSION = 3
DEFAULT_LEGACY_MAX_OBSERVATION_RECORDS = 10_000
DEFAULT_LEGACY_MAX_INCIDENT_STATES = 200
DEFAULT_LEGACY_MAX_INCIDENT_TRANSITION_RECORDS = 2_000
DEFAULT_LEGACY_MAX_OUTBOX_ITEMS = 1_000
DEFAULT_LEGACY_OUTBOX_MAX_ATTEMPTS = 3
DEFAULT_LEGACY_OUTBOX_RETRY_BACKOFF_SECONDS = 300.0
DEFAULT_LEGACY_OUTBOX_CLAIM_TIMEOUT_SECONDS = 600.0
COMMON_ENV_KEYS = {
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
STATE_ENV_KEYS = {
    "MONITORING_AGENT_MAX_OBSERVATION_RECORDS",
    "MONITORING_AGENT_MAX_INCIDENT_STATES",
    "MONITORING_AGENT_MAX_INCIDENT_TRANSITION_RECORDS",
    "MONITORING_AGENT_MAX_OUTBOX_ITEMS",
    "MONITORING_AGENT_OUTBOX_MAX_ATTEMPTS",
    "MONITORING_AGENT_OUTBOX_RETRY_BACKOFF_SECONDS",
    "MONITORING_AGENT_OUTBOX_CLAIM_TIMEOUT_SECONDS",
}
ENV_KEYS_BY_VERSION = {
    LEGACY_ENV_CONTRACT_VERSION: COMMON_ENV_KEYS,
    2: COMMON_ENV_KEYS | {"MONITORING_AGENT_EXTERNAL_WEB_URL"},
    ENV_CONTRACT_VERSION: (
        COMMON_ENV_KEYS | {"MONITORING_AGENT_EXTERNAL_WEB_URL"} | STATE_ENV_KEYS
    ),
}
ENV_KEYS = ENV_KEYS_BY_VERSION[ENV_CONTRACT_VERSION]
ENV_ENDPOINT_SET_VERSIONS = {
    LEGACY_ENV_CONTRACT_VERSION: 2,
    2: 3,
    ENV_CONTRACT_VERSION: 3,
}
ENDPOINT_SET_CONTRACT_VERSIONS = {
    endpoint_set_version: contract_version
    for contract_version, endpoint_set_version in CONTRACT_ENDPOINT_SET_VERSIONS.items()
}
ENV_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True)
class RuntimeSettings:
    env_contract_version: int
    mode: str
    instance_id: str
    base_url: str
    external_web_url: str | None
    state_dir: Path
    timeout_seconds: float
    max_attempts: int
    retry_backoff_seconds: float
    poll_interval_seconds: float
    poll_jitter_seconds: float
    endpoint_keys: tuple[str, ...]
    endpoint_set_version: int
    observation_contract_version: int
    max_observation_records: int
    max_incident_states: int
    max_incident_transition_records: int
    max_outbox_items: int
    outbox_max_attempts: int
    outbox_retry_backoff_seconds: float
    outbox_claim_timeout_seconds: float
    bearer_credential: str = field(repr=False)
    delivery_automation_enabled: bool = False

    @classmethod
    def load(cls, path: Path) -> RuntimeSettings:
        env_path = path.resolve()
        values = _read_strict_env(env_path)
        if "MONITORING_AGENT_ENV_VERSION" not in values:
            raise ValueError(
                "environment schema mismatch: "
                "missing=['MONITORING_AGENT_ENV_VERSION'], unexpected=[]"
            )
        env_version = _integer(
            values["MONITORING_AGENT_ENV_VERSION"],
            name="MONITORING_AGENT_ENV_VERSION",
        )
        if env_version not in ENV_KEYS_BY_VERSION:
            raise ValueError(f"unsupported environment contract: {env_version!r}")
        expected_env_keys = ENV_KEYS_BY_VERSION[env_version]
        actual_keys = set(values)
        if actual_keys != expected_env_keys:
            raise ValueError(
                "environment schema mismatch: "
                f"missing={sorted(expected_env_keys - actual_keys)!r}, "
                f"unexpected={sorted(actual_keys - expected_env_keys)!r}"
            )

        if values["MONITORING_AGENT_MODE"] != "test":
            raise ValueError("the observer supports only test mode")

        instance_id = values["MONITORING_AGENT_INSTANCE_ID"].strip()
        if not instance_id:
            raise ValueError("MONITORING_AGENT_INSTANCE_ID must not be empty")

        base_url = validate_base_url(values["MONITORING_AGENT_BASE_URL"])
        if base_url.startswith("https://example.invalid"):
            raise ValueError("MONITORING_AGENT_BASE_URL still contains a placeholder")

        external_web_url: str | None = None
        if "MONITORING_AGENT_EXTERNAL_WEB_URL" in values:
            external_web_url = validate_external_web_url(
                values["MONITORING_AGENT_EXTERNAL_WEB_URL"]
            )
            if external_web_url.startswith("https://example.invalid"):
                raise ValueError(
                    "MONITORING_AGENT_EXTERNAL_WEB_URL still contains a placeholder"
                )

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
        endpoint_set_version = ENV_ENDPOINT_SET_VERSIONS[env_version]
        expected_endpoint_keys = ENDPOINT_SETS[endpoint_set_version]
        if endpoint_keys != expected_endpoint_keys:
            raise ValueError(
                "MONITORING_AGENT_ENDPOINT_KEYS contains an unapproved or outdated "
                "endpoint set for the selected environment contract"
            )

        if env_version >= STATE_ENV_CONTRACT_VERSION:
            max_observation_records = _integer(
                values["MONITORING_AGENT_MAX_OBSERVATION_RECORDS"],
                name="MONITORING_AGENT_MAX_OBSERVATION_RECORDS",
            )
            max_incident_states = _integer(
                values["MONITORING_AGENT_MAX_INCIDENT_STATES"],
                name="MONITORING_AGENT_MAX_INCIDENT_STATES",
            )
            max_incident_transition_records = _integer(
                values["MONITORING_AGENT_MAX_INCIDENT_TRANSITION_RECORDS"],
                name="MONITORING_AGENT_MAX_INCIDENT_TRANSITION_RECORDS",
            )
            max_outbox_items = _integer(
                values["MONITORING_AGENT_MAX_OUTBOX_ITEMS"],
                name="MONITORING_AGENT_MAX_OUTBOX_ITEMS",
            )
            outbox_max_attempts = _integer(
                values["MONITORING_AGENT_OUTBOX_MAX_ATTEMPTS"],
                name="MONITORING_AGENT_OUTBOX_MAX_ATTEMPTS",
            )
            outbox_retry_backoff_seconds = _non_negative_number(
                values["MONITORING_AGENT_OUTBOX_RETRY_BACKOFF_SECONDS"],
                name="MONITORING_AGENT_OUTBOX_RETRY_BACKOFF_SECONDS",
            )
            outbox_claim_timeout_seconds = _positive_number(
                values["MONITORING_AGENT_OUTBOX_CLAIM_TIMEOUT_SECONDS"],
                name="MONITORING_AGENT_OUTBOX_CLAIM_TIMEOUT_SECONDS",
            )
        else:
            max_observation_records = DEFAULT_LEGACY_MAX_OBSERVATION_RECORDS
            max_incident_states = DEFAULT_LEGACY_MAX_INCIDENT_STATES
            max_incident_transition_records = (
                DEFAULT_LEGACY_MAX_INCIDENT_TRANSITION_RECORDS
            )
            max_outbox_items = DEFAULT_LEGACY_MAX_OUTBOX_ITEMS
            outbox_max_attempts = DEFAULT_LEGACY_OUTBOX_MAX_ATTEMPTS
            outbox_retry_backoff_seconds = (
                DEFAULT_LEGACY_OUTBOX_RETRY_BACKOFF_SECONDS
            )
            outbox_claim_timeout_seconds = DEFAULT_LEGACY_OUTBOX_CLAIM_TIMEOUT_SECONDS
        if max_observation_records < len(endpoint_keys):
            raise ValueError(
                "MONITORING_AGENT_MAX_OBSERVATION_RECORDS must retain at least "
                "one complete endpoint cycle"
            )
        for name, value in {
            "MONITORING_AGENT_MAX_INCIDENT_STATES": max_incident_states,
            "MONITORING_AGENT_MAX_INCIDENT_TRANSITION_RECORDS": (
                max_incident_transition_records
            ),
            "MONITORING_AGENT_MAX_OUTBOX_ITEMS": max_outbox_items,
            "MONITORING_AGENT_OUTBOX_MAX_ATTEMPTS": outbox_max_attempts,
        }.items():
            if value < 1:
                raise ValueError(f"{name} must be positive")

        bearer_credential = values["MONITORING_AGENT_BEARER_TOKEN"]
        if (
            len(bearer_credential) < 32
            or any(character.isspace() for character in bearer_credential)
            or "change-me" in bearer_credential.lower()
        ):
            raise ValueError("MONITORING_AGENT_BEARER_TOKEN has an invalid format")
        delivery_automation_enabled = _read_delivery_automation_enabled(env_path)

        return cls(
            env_contract_version=env_version,
            mode="test",
            instance_id=instance_id,
            base_url=base_url,
            external_web_url=external_web_url,
            state_dir=state_dir,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
            poll_interval_seconds=poll_interval_seconds,
            poll_jitter_seconds=poll_jitter_seconds,
            endpoint_keys=endpoint_keys,
            endpoint_set_version=endpoint_set_version,
            observation_contract_version=(
                ENDPOINT_SET_CONTRACT_VERSIONS[endpoint_set_version]
            ),
            max_observation_records=max_observation_records,
            max_incident_states=max_incident_states,
            max_incident_transition_records=max_incident_transition_records,
            max_outbox_items=max_outbox_items,
            outbox_max_attempts=outbox_max_attempts,
            outbox_retry_backoff_seconds=outbox_retry_backoff_seconds,
            outbox_claim_timeout_seconds=outbox_claim_timeout_seconds,
            bearer_credential=bearer_credential,
            delivery_automation_enabled=delivery_automation_enabled,
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
        if not key.startswith("MONITORING_AGENT_"):
            continue
        if key in values:
            raise ValueError(f"environment key is duplicated: {key}")
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _read_delivery_automation_enabled(path: Path) -> bool:
    values = _read_non_monitoring_keys(path, {"DELIVERY_AUTOMATION_ENABLED"})
    raw_value = values.get("DELIVERY_AUTOMATION_ENABLED")
    if raw_value is None:
        return False
    normalized = raw_value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError("DELIVERY_AUTOMATION_ENABLED must be either true or false")


def _read_non_monitoring_keys(path: Path, allowed_keys: set[str]) -> dict[str, str]:
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
        if key.startswith("MONITORING_AGENT_") or key not in allowed_keys:
            continue
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
