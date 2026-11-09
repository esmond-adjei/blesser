import base64
import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from api.core.config import settings

log = logging.getLogger(__name__)


def fernet() -> Fernet:
    secret = settings.secrets_key
    if not secret:
        if settings.app_env.lower() in ("production", "prod"):
            raise RuntimeError("SECRETS_KEY is required in production")
        path = Path(settings.upload_dir) / ".dev-secrets-key"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not path.exists():
            with tempfile.NamedTemporaryFile(
                mode="w", dir=path.parent, prefix=".dev-key-"
            ) as handle:
                handle.write(Fernet.generate_key().decode())
                handle.flush()
                try:
                    os.link(handle.name, path)
                except FileExistsError:
                    pass
            log.warning(
                "SECRETS_KEY is empty: using the local development key at %s", path
            )
        secret = path.read_text()
    digest = hashlib.sha256(b"blesser-applicant-kit:" + secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class EncryptedSensitive(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return (
            fernet().encrypt(json.dumps(value).encode()).decode()
            if value is not None
            else None
        )

    def process_result_value(self, value, dialect):
        return (
            json.loads(fernet().decrypt(value.encode())) if value is not None else None
        )
