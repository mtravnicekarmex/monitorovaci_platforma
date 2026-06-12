from __future__ import annotations

from functools import lru_cache
import hashlib
import hmac
from pathlib import Path
import secrets
import unicodedata


HASH_NAME = "sha256"
PBKDF2_ITERATIONS = 600000
SALT_BYTES = 16
MIN_PASSWORD_LENGTH = 15
MAX_PASSWORD_LENGTH = 1024
PASSWORD_BLOCKLIST_PATH = Path(__file__).with_name("password_blocklist.txt")
PASSWORD_POLICY_HELP = (
    "Alespon 15 znaku. Povoleny jsou mezery, Unicode a dlouhe passphrase; "
    "bezna nebo kompromitovana hesla jsou blokovana."
)


class PasswordPolicyError(ValueError):
    """Raised when a prospective dashboard password violates the shared policy."""


def normalize_password(password: str) -> str:
    return unicodedata.normalize("NFC", password)


def _normalize_blocklist_value(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).casefold()
    return " ".join(normalized.split())


@lru_cache(maxsize=1)
def load_password_blocklist() -> frozenset[str]:
    try:
        entries = PASSWORD_BLOCKLIST_PATH.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(
            f"Nepodarilo se nacist lokalni password blocklist: {PASSWORD_BLOCKLIST_PATH}"
        ) from exc

    return frozenset(
        normalized
        for entry in entries
        if entry.strip() and not entry.lstrip().startswith("#")
        if (normalized := _normalize_blocklist_value(entry))
    )


def validate_password(password: str, *, username: str | None = None) -> str:
    if not isinstance(password, str):
        raise PasswordPolicyError("Heslo musi byt textova hodnota.")

    normalized = normalize_password(password)
    if len(normalized) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Heslo musi mit alespon {MIN_PASSWORD_LENGTH} znaku."
        )
    if len(normalized) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Heslo muze mit nejvyse {MAX_PASSWORD_LENGTH} znaku."
        )
    if not normalized.strip():
        raise PasswordPolicyError("Heslo nesmi obsahovat pouze mezery.")

    comparable = _normalize_blocklist_value(normalized)
    blocked_values = set(load_password_blocklist())
    if username:
        comparable_username = _normalize_blocklist_value(username)
        if comparable_username:
            blocked_values.update(
                {
                    comparable_username,
                    comparable_username * 2,
                    comparable_username * 3,
                }
            )

    if comparable in blocked_values:
        raise PasswordPolicyError(
            "Heslo je na seznamu bezne pouzivanych nebo kompromitovanych hesel."
        )
    return normalized


def _parse_password_hash(password_hash: str) -> tuple[str, int, str, str] | None:
    try:
        algorithm, iteration_text, salt, expected_digest = password_hash.split("$", 3)
        iterations = int(iteration_text)
    except (AttributeError, TypeError, ValueError):
        return None

    if (
        algorithm != f"pbkdf2_{HASH_NAME}"
        or iterations <= 0
        or not salt
        or not expected_digest
    ):
        return None
    return algorithm, iterations, salt, expected_digest


def hash_password(password: str) -> str:
    normalized = normalize_password(password)
    salt = secrets.token_hex(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        HASH_NAME,
        normalized.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2_{HASH_NAME}${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    parsed = _parse_password_hash(password_hash)
    if parsed is None:
        return False
    _algorithm, iterations, salt, expected_digest = parsed

    candidates = tuple(dict.fromkeys((password, normalize_password(password))))
    for candidate in candidates:
        actual_digest = hashlib.pbkdf2_hmac(
            HASH_NAME,
            candidate.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()
        if hmac.compare_digest(actual_digest, expected_digest):
            return True
    return False


def password_hash_needs_rehash(password_hash: str) -> bool:
    parsed = _parse_password_hash(password_hash)
    if parsed is None:
        return False
    _algorithm, iterations, _salt, _expected_digest = parsed
    return iterations < PBKDF2_ITERATIONS
