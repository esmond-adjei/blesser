"""Third-party sign-in (OAuth 2.0 authorization code + PKCE).

A known (provider, subject) signs straight in. A new identity whose verified
email matches no account creates one. One whose email matches an existing
account is never merged silently: the person proves that account's password
first (one person, one account).
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy import select

from api.auth import models as auth_models
from api.auth import security as auth_security
from api.core.config import settings
from api.core.exceptions import AuthError, BadRequestError, NotFoundError
from api.core.time import utcnow_naive

STATE_TTL = timedelta(minutes=10)
LINK_TTL = timedelta(minutes=10)
# Passwordless accounts store a value bcrypt can never match.
NO_PASSWORD = "!oauth-only"


@dataclass(frozen=True)
class Profile:
    subject: str
    email: str
    email_verified: bool
    name: str | None = None


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scopes: tuple[str, ...]
    extra_params: dict = field(default_factory=dict)

    @property
    def client_id(self) -> str:
        return getattr(settings, f"oauth_{self.id}_client_id", "")

    @property
    def client_secret(self) -> str:
        return getattr(settings, f"oauth_{self.id}_client_secret", "")

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def profile(self, data: dict) -> Profile:
        # OpenID Connect userinfo shape (Google); other providers override.
        return Profile(
            subject=str(data["sub"]),
            email=str(data.get("email") or "").strip().lower(),
            email_verified=bool(data.get("email_verified")),
            name=data.get("name"),
        )


PROVIDERS: dict[str, Provider] = {
    "google": Provider(
        id="google",
        label="Google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
        scopes=("openid", "email", "profile"),
        extra_params={"prompt": "select_account"},
    ),
}


def get_provider(provider_id: str) -> Provider:
    p = PROVIDERS.get(provider_id)
    if p is None or not p.enabled:
        raise NotFoundError("That sign-in method isn't available.")
    return p


def enabled_providers() -> list[dict]:
    return [{"id": p.id, "label": p.label} for p in PROVIDERS.values() if p.enabled]


def redirect_uri(provider_id: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}/auth/callback/{provider_id}"


def start(provider_id: str, next_path: str = "/") -> dict:
    """Authorize URL plus the signed state the client must echo back."""
    p = get_provider(provider_id)
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    safe_next = (
        next_path
        if next_path.startswith("/") and not next_path.startswith("//")
        else "/"
    )
    state = auth_security.signed_token(
        "oauth_state",
        {"p": p.id, "v": verifier, "n": safe_next, "x": secrets.token_urlsafe(8)},
        STATE_TTL,
    )
    params = {
        "client_id": p.client_id,
        "redirect_uri": redirect_uri(p.id),
        "response_type": "code",
        "scope": " ".join(p.scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        **p.extra_params,
    }
    return {"authorize_url": f"{p.authorize_url}?{urlencode(params)}", "state": state}


async def exchange(p: Provider, code: str, verifier: str) -> Profile:
    """Code -> tokens -> profile, straight from the provider over TLS."""
    async with httpx.AsyncClient(timeout=15) as client:
        token = await client.post(
            p.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(p.id),
                "client_id": p.client_id,
                "client_secret": p.client_secret,
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
        )
        if token.status_code != 200:
            raise AuthError(f"{p.label} sign-in failed. Try again.")
        access = token.json().get("access_token")
        info = await client.get(
            p.userinfo_url, headers={"Authorization": f"Bearer {access}"}
        )
        if info.status_code != 200:
            raise AuthError(f"{p.label} sign-in failed. Try again.")
        return p.profile(info.json())


async def complete(session, provider_id: str, code: str, state: str) -> dict:
    """Finish sign-in. Returns {"user": User} to sign in, or
    {"link_required": {...}} when an existing account must be proven."""
    claims = auth_security.read_signed("oauth_state", state)
    if claims is None or claims.get("p") != provider_id:
        raise BadRequestError("This sign-in attempt expired. Start again.")
    p = get_provider(provider_id)
    profile = await exchange(p, code, claims["v"])
    if not profile.email or not profile.email_verified:
        raise BadRequestError(
            f"Your {p.label} account has no verified email we can use."
        )

    identity = (
        await session.execute(
            select(auth_models.UserIdentity).where(
                auth_models.UserIdentity.provider == p.id,
                auth_models.UserIdentity.subject == profile.subject,
            )
        )
    ).scalar_one_or_none()
    if identity is not None:
        user = await session.get(auth_models.User, identity.user_id)
        return {"user": user, "next": claims.get("n", "/")}

    existing = (
        await session.execute(
            select(auth_models.User).where(auth_models.User.email == profile.email)
        )
    ).scalar_one_or_none()
    if existing is not None:
        link = auth_security.signed_token(
            "oauth_link",
            {"p": p.id, "s": profile.subject, "e": profile.email, "u": existing.id},
            LINK_TTL,
        )
        return {
            "link_required": {
                "provider": p.label,
                "email": profile.email,
                "link_token": link,
            },
            "next": claims.get("n", "/"),
        }

    user = auth_models.User(
        email=profile.email,
        password_hash=NO_PASSWORD,
        display_name=(profile.name or None) and profile.name[:80],
        email_verified_at=utcnow_naive(),
        # The sign-in buttons say continuing accepts the Terms; record which version.
        terms_accepted_at=utcnow_naive(),
        terms_version=settings.terms_version,
    )
    session.add(user)
    await session.flush()
    session.add(
        auth_models.UserIdentity(
            user_id=user.id, provider=p.id, subject=profile.subject, email=profile.email
        )
    )
    await session.commit()
    return {"user": user, "next": claims.get("n", "/")}


async def link(session, link_token: str, password: str) -> auth_models.User:
    """Attach a pending identity after proving the existing account."""
    claims = auth_security.read_signed("oauth_link", link_token)
    if claims is None:
        raise BadRequestError("This link request expired. Sign in with Google again.")
    user = await session.get(auth_models.User, claims["u"])
    if user is None or not auth_security.check_password(password, user.password_hash):
        raise AuthError("Password is incorrect.")
    already = (
        await session.execute(
            select(auth_models.UserIdentity).where(
                auth_models.UserIdentity.provider == claims["p"],
                auth_models.UserIdentity.subject == claims["s"],
            )
        )
    ).scalar_one_or_none()
    if already is None:
        session.add(
            auth_models.UserIdentity(
                user_id=user.id,
                provider=claims["p"],
                subject=claims["s"],
                email=claims["e"],
            )
        )
    # Google verified the mailbox, and the password proved the account.
    user.email_verified_at = user.email_verified_at or utcnow_naive()
    await session.commit()
    return user
