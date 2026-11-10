"""Auth primitives: password hashing, JWT access tokens, refresh tokens, login throttle.

AUTH_SECRET signs access tokens. Empty in dev means an ephemeral secret, so
production must set it or every restart invalidates all sessions.
"""

import hashlib
import logging
import secrets
import time
from datetime import datetime, timedelta

import bcrypt
import jwt

from api.core.config import settings
from api.core.time import utcnow_naive

log = logging.getLogger(__name__)

if settings.auth_secret:
    _SIGNING_KEY = settings.auth_secret
else:
    _SIGNING_KEY = secrets.token_hex(32)
    log.warning(
        "AUTH_SECRET is empty: generated an ephemeral signing key. "
        "Sessions die on restart; set AUTH_SECRET in production."
    )


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def issue_access_token(
    user_id: str, audience: str = "app", *, session_id: str | None = None
) -> str:
    expiry = utcnow_naive() + timedelta(minutes=settings.auth_access_minutes)
    return jwt.encode(
        {
            "sub": user_id,
            "exp": expiry,
            "iat": utcnow_naive(),
            "aud": audience,
            **({"sid": session_id} if session_id else {}),
        },
        _SIGNING_KEY,
        algorithm="HS256",
    )


def parse_access_token(token: str, audience: str = "app") -> str | None:
    """User id for a valid token, else None (expired, forged, or garbage)."""
    payload = parse_access_claims(token, audience)
    return payload["sub"] if payload else None


def parse_access_claims(token: str, audience: str = "app") -> dict | None:
    try:
        payload = jwt.decode(
            token,
            _SIGNING_KEY,
            algorithms=["HS256"],
            audience=audience,
            options={"require": ["aud", "exp", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    # Purpose-typed tokens (OAuth state, link tokens) are never sessions.
    if payload.get("typ") is not None:
        return None
    sub = payload.get("sub")
    return payload if isinstance(sub, str) and sub else None


def signed_token(typ: str, claims: dict, ttl: timedelta) -> str:
    """Short-lived signed token for one purpose (e.g. OAuth state)."""
    return jwt.encode(
        {**claims, "typ": typ, "exp": utcnow_naive() + ttl, "iat": utcnow_naive()},
        _SIGNING_KEY,
        algorithm="HS256",
    )


def read_signed(typ: str, token: str) -> dict | None:
    """Claims of a valid, unexpired token of this purpose, else None."""
    try:
        payload = jwt.decode(token, _SIGNING_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return payload if payload.get("typ") == typ else None


def new_refresh_token(audience: str = "app") -> tuple[str, str, datetime]:
    """(presented token, stored hash, expiry). Only the hash hits the DB."""
    raw = secrets.token_urlsafe(48)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    expiry = utcnow_naive() + (
        timedelta(hours=12)
        if audience == "admin"
        else timedelta(days=90 if audience == "ext" else settings.auth_refresh_days)
    )
    return raw, digest, expiry


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# Login throttle: per-email failure timestamps (Unix seconds), in-process only;
# a restart forgets past failures.
_attempts: dict[str, list[float]] = {}


def login_allowed(email: str) -> bool:
    now = time.monotonic()
    window = now - settings.auth_login_window_seconds
    recent = [t for t in _attempts.get(email.lower(), []) if t > window]
    _attempts[email.lower()] = recent
    return len(recent) < settings.auth_login_attempts


def record_login_failure(email: str) -> None:
    _attempts.setdefault(email.lower(), []).append(time.monotonic())


def clear_login_failures(email: str) -> None:
    _attempts.pop(email.lower(), None)
