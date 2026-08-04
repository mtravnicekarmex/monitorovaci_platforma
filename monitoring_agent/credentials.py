from __future__ import annotations

from pathlib import Path


def load_bearer_credential(path: Path) -> str:
    try:
        raw_value = path.resolve().read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError("credential file could not be read") from exc
    credential = raw_value.strip()
    if not credential or len(credential) < 32:
        raise ValueError("credential must contain at least 32 characters")
    if any(character.isspace() for character in credential):
        raise ValueError("credential must be a single value without whitespace")
    return credential
