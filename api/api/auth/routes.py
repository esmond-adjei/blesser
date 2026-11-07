"""Auth routes: accounts, sessions, passwords and profile."""

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Request,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import email_flows
from api.auth import oauth as auth_oauth
from api.auth import profile as auth_profile
from api.auth import schemas as auth_schemas
from api.auth import security as auth_security
from api.auth import service as auth_service
from api.core import mailer
from api.core.db import get_session
from api.core.exceptions import AuthError

router = APIRouter(tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> auth_schemas.UserOut:
    """Bearer identity for protected routes. Missing, expired, or forged
    tokens 401; unknown users 401 (their grants die with them)."""
    if credentials is None or not credentials.credentials:
        raise AuthError("Sign in required.")
    return await _user_for_token(session, credentials.credentials)


async def _user_for_token(session: AsyncSession, token: str) -> auth_schemas.UserOut:
    user_id = auth_security.parse_access_token(token)
    if user_id is None:
        raise AuthError("Session expired or invalid; sign in again.")
    user = await auth_service.get_user_or_401(session, user_id)
    return auth_schemas.UserOut(**auth_service.to_user_out(user))


async def get_sse_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> auth_schemas.UserOut:
    """Bearer identity for EventSource streams: token may ride `?token=` (headers win)."""
    token = None
    if credentials is not None and credentials.credentials:
        token = credentials.credentials
    if not token:
        token = request.query_params.get("token")
    if not token:
        raise AuthError("Sign in required.")
    return await _user_for_token(session, token)


@router.post("/auth/register")
async def register(
    req: auth_schemas.RegisterIn,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Create an account and sign in; it works unverified until the email is verified."""
    result = await auth_service.register(
        session, req.email, req.password, req.accept_terms
    )
    user = await auth_service.get_user_or_401(session, result["user"]["id"])
    background.add_task(mailer.send, await email_flows.verification_mail(session, user))
    return {
        "user": auth_schemas.UserOut(**result["user"]),
        "tokens": auth_schemas.TokenPair(**result["tokens"]),
    }


@router.post("/auth/login")
async def login(
    req: auth_schemas.LoginIn, session: AsyncSession = Depends(get_session)
):
    """Sign in with email + password. Repeated failures lock the email out briefly."""
    result = await auth_service.login(session, req.email, req.password)
    return {
        "user": auth_schemas.UserOut(**result["user"]),
        "tokens": auth_schemas.TokenPair(**result["tokens"]),
    }


@router.post("/auth/refresh")
async def refresh(
    req: auth_schemas.RefreshIn, session: AsyncSession = Depends(get_session)
):
    """Swap a refresh grant for a fresh pair; the presented grant dies on use."""
    result = await auth_service.refresh(session, req.refresh_token)
    return {
        "user": auth_schemas.UserOut(**result["user"]),
        "tokens": auth_schemas.TokenPair(**result["tokens"]),
    }


@router.post("/auth/logout")
async def logout(
    req: auth_schemas.LogoutIn, session: AsyncSession = Depends(get_session)
):
    """Revoke a refresh grant and this device's push subscription; unknown grants succeed."""
    return await auth_service.logout(session, req.refresh_token, req.push_endpoint)


@router.get("/auth/oauth/providers")
async def oauth_providers():
    """Sign-in providers configured on this server."""
    return auth_oauth.enabled_providers()


@router.post("/auth/oauth/{provider}/start")
async def oauth_start(provider: str, req: auth_schemas.OAuthStartIn):
    """Provider authorize URL plus a signed, expiring state to echo back."""
    return auth_oauth.start(provider, req.next)


@router.post("/auth/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    req: auth_schemas.OAuthCallbackIn,
    session: AsyncSession = Depends(get_session),
):
    """Finish provider sign-in, or `link_required` when the email has an account."""
    result = await auth_oauth.complete(session, provider, req.code, req.state)
    if "link_required" in result:
        return {"link_required": result["link_required"], "next": result["next"]}
    tokens = await auth_service.issue_pair(session, result["user"])
    return {
        "user": auth_schemas.UserOut(**auth_service.to_user_out(result["user"])),
        "tokens": auth_schemas.TokenPair(**tokens),
        "next": result["next"],
    }


@router.post("/auth/oauth/link")
async def oauth_link(req: auth_schemas.OAuthLinkIn, session: AsyncSession = Depends(get_session)):
    """Attach a pending provider identity by proving the existing account's password."""
    user = await auth_oauth.link(session, req.link_token, req.password)
    tokens = await auth_service.issue_pair(session, user)
    return {
        "user": auth_schemas.UserOut(**auth_service.to_user_out(user)),
        "tokens": auth_schemas.TokenPair(**tokens),
    }


@router.post("/auth/password/forgot")
async def forgot_password(
    req: auth_schemas.ForgotPasswordIn,
    request: Request,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Email a reset link; same answer and timing whether or not the account exists."""
    from api.core.ratelimit import enforce

    enforce("reset_email", str(req.email).strip().lower())
    enforce("reset_ip", request.client.host if request.client else "unknown")
    mail = await email_flows.request_password_reset(session, str(req.email))
    if mail is not None:
        background.add_task(mailer.send, mail)
    return {"status": "If an account exists for that email, a reset link is on its way."}


@router.post("/auth/password/reset")
async def reset_password(
    req: auth_schemas.ResetPasswordIn, session: AsyncSession = Depends(get_session)
):
    """Set a new password from an emailed link. Single use; signs every session out."""
    await email_flows.reset_password(session, req.token, req.new_password)
    return {"status": "Password updated. Sign in with your new password."}


@router.post("/auth/verify/send")
async def send_verification(
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Resend the verification link (cooldown between sends)."""
    user = await auth_service.get_user_or_401(session, current.id)
    background.add_task(mailer.send, await email_flows.resend_verification(session, user))
    return {"status": f"Sent a new link to {user.email}."}


@router.post("/auth/verify", response_model=auth_schemas.UserOut)
async def verify_email(
    req: auth_schemas.VerifyEmailIn, session: AsyncSession = Depends(get_session)
):
    """Confirm an email address from its emailed link. Works signed out."""
    user = await email_flows.verify_email(session, req.token)
    return auth_schemas.UserOut(**auth_service.to_user_out(user))


@router.get("/auth/me", response_model=auth_schemas.UserOut)
async def get_me(current: auth_schemas.UserOut = Depends(get_current_user)):
    """Who this Bearer token belongs to."""
    return current


@router.patch("/auth/me", response_model=auth_schemas.UserOut)
async def update_me(
    req: auth_schemas.ProfileUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Set your display name (empty clears it) and the default-model preference."""
    user = await auth_service.get_user_or_401(session, current.id)
    # Only fields sent: toggling the model preference must not clear the name.
    if "display_name" in req.model_fields_set:
        await auth_profile.update_profile(session, user, req.display_name)
    await session.commit()
    return auth_schemas.UserOut(**auth_service.to_user_out(user))


@router.post("/auth/change-password")
async def change_password(
    req: auth_schemas.ChangePasswordIn,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Change password after proving the current one; other sessions stay active."""
    return await auth_service.change_password(
        session, current.id, req.current_password, req.new_password
    )


@router.delete("/auth/account")
async def delete_account(
    req: auth_schemas.DeleteAccountIn,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Delete the account after proving the password; every owned row cascades."""
    return await auth_service.delete_account(session, current.id, req.password)
