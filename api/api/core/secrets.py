"""Encryption at rest for stored secrets (provider API keys).

`EncryptedString` Fernet-encrypts on write ("enc:v1:<token>") and decrypts on
read; legacy plaintext rows still read as-is. Key: SECRETS_KEY, else derived
from AUTH_SECRET. With neither, values stay plaintext (with a warning): an
ephemeral key would make them unreadable after a restart.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from api.core.config import settings

log = logging.getLogger(__name__)
PREFIX = "enc:v1:"
_warned = False


def _fernet() -> Fernet | None:
    global _warned
    if settings.secrets_key:
        return Fernet(settings.secrets_key.encode())
    if settings.auth_secret:
        digest = hashlib.sha256(
            b"graduator-secrets:" + settings.auth_secret.encode()
        ).digest()
        return Fernet(base64.urlsafe_b64encode(digest))
    if not _warned:
        log.warning(
            "No SECRETS_KEY or AUTH_SECRET: provider API keys are stored unencrypted."
        )
        _warned = True
    return None


def encrypt(value: str) -> str:
    if not value or value.startswith(PREFIX):
        return value
    f = _fernet()
    return PREFIX + f.encrypt(value.encode()).decode() if f else value


class SecretUnavailable(RuntimeError):
    """A stored secret exists but can't be read with the current key."""


def decrypt(value: str) -> str:
    if not value or not value.startswith(PREFIX):
        return value  # legacy plaintext (or empty)
    f = _fernet()
    if f is None:
        raise SecretUnavailable(
            "An encrypted secret exists but no SECRETS_KEY/AUTH_SECRET is set."
        )
    try:
        return f.decrypt(value[len(PREFIX) :].encode()).decode()
    except InvalidToken as exc:
        raise SecretUnavailable(
            "Stored secret can't be decrypted: SECRETS_KEY/AUTH_SECRET changed."
        ) from exc


class EncryptedString(TypeDecorator):
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt(value) if isinstance(value, str) else value

    def process_result_value(self, value, dialect):
        return decrypt(value) if isinstance(value, str) else value
