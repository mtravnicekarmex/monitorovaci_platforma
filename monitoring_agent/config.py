from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .client import APPROVED_ENDPOINTS, validate_base_url


CONFIG_VERSION = 1
CONFIG_KEYS = {
    "config_version",
    "mode",
    "instance_id",
    "base_url",
    "state_dir",
    "timeout_seconds",
    "poll_interval_seconds",
    "endpoint_keys",
}


@dataclass(frozen=True)
class AgentConfig:
    config_version: int
    mode: str
    instance_id: str
    base_url: str
    state_dir: Path
    timeout_seconds: float
    poll_interval_seconds: float
    endpoint_keys: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> AgentConfig:
        config_path = path.resolve()
        try:
            decoded = json.loads(config_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError("configuration file could not be read") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("configuration file is not valid JSON") from exc

        if not isinstance(decoded, dict) or not all(
            isinstance(key, str) for key in decoded
        ):
            raise ValueError("configuration must be a JSON object")
        actual_keys = set(decoded)
        if actual_keys != CONFIG_KEYS:
            raise ValueError(
                "configuration schema mismatch: "
                f"missing={sorted(CONFIG_KEYS - actual_keys)!r}, "
                f"unexpected={sorted(actual_keys - CONFIG_KEYS)!r}"
            )

        config_version = decoded["config_version"]
        if config_version != CONFIG_VERSION:
            raise ValueError(f"unsupported config_version: {config_version!r}")
        if decoded["mode"] != "test":
            raise ValueError("the skeleton supports only mode='test'")

        instance_id = decoded["instance_id"]
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must be a non-empty string")

        base_url = decoded["base_url"]
        if not isinstance(base_url, str):
            raise ValueError("base_url must be a string")
        validated_base_url = validate_base_url(base_url)

        raw_state_dir = decoded["state_dir"]
        if not isinstance(raw_state_dir, str) or not raw_state_dir.strip():
            raise ValueError("state_dir must be a non-empty string")
        state_dir = Path(raw_state_dir)
        if not state_dir.is_absolute():
            state_dir = config_path.parent / state_dir

        timeout_seconds = _positive_number(
            decoded["timeout_seconds"],
            name="timeout_seconds",
        )
        poll_interval_seconds = _positive_number(
            decoded["poll_interval_seconds"],
            name="poll_interval_seconds",
        )

        raw_endpoint_keys = decoded["endpoint_keys"]
        if not isinstance(raw_endpoint_keys, list) or not raw_endpoint_keys:
            raise ValueError("endpoint_keys must be a non-empty array")
        if not all(isinstance(value, str) for value in raw_endpoint_keys):
            raise ValueError("endpoint_keys must contain only strings")
        endpoint_keys = tuple(raw_endpoint_keys)
        if len(set(endpoint_keys)) != len(endpoint_keys):
            raise ValueError("endpoint_keys must not contain duplicates")
        unknown = set(endpoint_keys) - set(APPROVED_ENDPOINTS)
        if unknown:
            raise ValueError(f"endpoint_keys contains unapproved values: {sorted(unknown)!r}")

        return cls(
            config_version=CONFIG_VERSION,
            mode="test",
            instance_id=instance_id.strip(),
            base_url=validated_base_url,
            state_dir=state_dir.resolve(),
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            endpoint_keys=endpoint_keys,
        )


def _positive_number(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    resolved = float(value)
    if resolved <= 0:
        raise ValueError(f"{name} must be positive")
    return resolved
