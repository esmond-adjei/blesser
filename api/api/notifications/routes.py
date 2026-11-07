"""Notification routes: inbox, preferences, push subscriptions, unsubscribe link."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import models as auth_models
from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core import mailer
from api.core.config import settings
from api.core.db import get_session
from api.core.exceptions import BadRequestError, NotFoundError
from api.core.ids import new_id
from api.core.mail_layout import compose
from api.core.ratelimit import rate_limit
from api.core.time import utcnow_naive
from api.notifications import delivery, push
from api.notifications import models as notification_models
from api.notifications import schemas as notification_schemas
from api.notifications import service as notification_service

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=notification_schemas.InboxOut)
async def list_notifications(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """The inbox: newest 30 plus the unread count. The web app polls this."""
    return await notification_service.list_inbox(session, current.id)


@router.post("/notifications/read-all")
async def read_all(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return {"marked": await notification_service.mark_read(session, current.id)}


@router.post("/notifications/{notification_id}/read")
async def read_one(
    notification_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return {
        "marked": await notification_service.mark_read(session, current.id, notification_id)
    }


@router.get("/notifications/preferences", response_model=notification_schemas.PreferencesOut)
async def get_preferences(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Channels per event (defaults filled in), quiet hours, timezone."""
    return notification_service.prefs_out(
        await notification_service.get_prefs(session, current.id)
    )


@router.patch("/notifications/preferences", response_model=notification_schemas.PreferencesOut)
async def update_preferences(
    req: notification_schemas.PreferencesIn,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await notification_service.update_prefs(
        session, current.id, req.model_dump(exclude_unset=True)
    )


@router.get("/notifications/push/config", response_model=notification_schemas.PushConfigOut)
async def push_config(current: auth_schemas.UserOut = Depends(get_current_user)):
    """VAPID public key for subscribing; disabled while the server has no keys."""
    enabled = push.push_configured()
    return {"enabled": enabled, "public_key": settings.vapid_public_key if enabled else None}


@router.get(
    "/notifications/push/subscriptions",
    response_model=list[notification_schemas.PushSubscriptionOut],
)
async def list_subscriptions(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    rows = await session.execute(
        select(notification_models.PushSubscription)
        .where(notification_models.PushSubscription.user_id == current.id)
        .order_by(notification_models.PushSubscription.created_at.desc())
    )
    return rows.scalars().all()


@router.post(
    "/notifications/push/subscriptions",
    response_model=notification_schemas.PushSubscriptionOut,
)
async def subscribe(
    req: notification_schemas.PushSubscriptionIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Save this browser's subscription; an endpoint from another account moves here."""
    table = notification_models.PushSubscription
    user_agent = (request.headers.get("user-agent") or "")[:300] or None
    values = {
        "user_id": current.id,
        "p256dh": req.keys.p256dh,
        "auth": req.keys.auth,
        "user_agent": user_agent,
    }
    await session.execute(
        pg_insert(table)
        .values(id=new_id(), endpoint=req.endpoint, **values)
        .on_conflict_do_update(index_elements=[table.endpoint], set_=values)
    )
    if req.timezone and notification_service.valid_zone(req.timezone):
        prefs = await notification_service.ensure_prefs(session, current.id)
        prefs.timezone = prefs.timezone or req.timezone
    await session.commit()
    row = (
        await session.execute(select(table).where(table.endpoint == req.endpoint))
    ).scalar_one()
    return row


@router.delete("/notifications/push/subscriptions")
async def unsubscribe(
    req: notification_schemas.PushEndpointIn,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Remove one of the account's devices (by its endpoint)."""
    result = await session.execute(
        delete(notification_models.PushSubscription).where(
            notification_models.PushSubscription.user_id == current.id,
            notification_models.PushSubscription.endpoint == req.endpoint,
        )
    )
    await session.commit()
    return {"removed": result.rowcount or 0}


@router.post(
    "/notifications/test",
    response_model=notification_schemas.TestResultOut,
    dependencies=[Depends(rate_limit("test_notification"))],
)
async def send_test(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Push a test notification to every device now (ignores quiet hours and cap)."""
    await notification_service.notify(
        session,
        user_id=current.id,
        kind="test",
        title="Test notification",
        body="Notifications from Graduator reach this device.",
        link="/new?settings=notifications",
        dedupe_key=f"test:{uuid.uuid4().hex}",
    )
    row = (
        await session.execute(
            select(notification_models.Notification)
            .where(
                notification_models.Notification.user_id == current.id,
                notification_models.Notification.kind == "test",
            )
            .order_by(notification_models.Notification.created_at.desc())
            .limit(1)
        )
    ).scalar_one()
    devices = (
        await session.execute(
            select(notification_models.PushSubscription.id).where(
                notification_models.PushSubscription.user_id == current.id
            )
        )
    ).all()
    now = utcnow_naive()
    pushed = await delivery.push_to_user(session, row, now)
    row.delivered_at, row.delivery = now, "push" if pushed else "none"
    await session.commit()
    return {
        "push_enabled": push.push_configured(),
        "devices": len(devices),
        "pushed": pushed,
    }


@router.post(
    "/notifications/test-email",
    response_model=notification_schemas.TestEmailOut,
    dependencies=[Depends(rate_limit("test_notification"))],
)
async def send_test_email(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Email the signed-in user now (ignores quiet hours, cap and email settings)."""
    user = await session.get(auth_models.User, current.id)
    if user is None or user.email_verified_at is None:
        raise BadRequestError("Verify your email address first; notifications only go to verified addresses.")
    sent = await mailer.send(
        compose(
            to=user.email,
            subject="Test email from Graduator",
            eyebrow="Test",
            heading="Email notifications work",
            paragraphs=["This address receives Graduator notifications. Choose which events email you in your notification settings."],
            action=("Open notification settings", delivery.settings_link()),
        )
    )
    return {"to": user.email, "sent": sent, "backend": settings.mail_backend}


@router.post("/notifications/unsubscribe")
async def unsubscribe_email(
    req: notification_schemas.UnsubscribeIn,
    session: AsyncSession = Depends(get_session),
):
    """Email footer link (no sign-in): turns email off for the signed kind."""
    claims = delivery.read_unsubscribe(req.token)
    if claims is None:
        raise BadRequestError("This unsubscribe link is invalid or has expired.")
    user_id, kind = claims
    if kind != notification_service.DIGEST and kind not in notification_service.KINDS:
        raise NotFoundError("Unknown notification kind")
    from api.auth import models as auth_models

    if await session.get(auth_models.User, user_id) is None:
        raise NotFoundError("Account not found")
    label = await notification_service.unsubscribe_email(session, user_id, kind)
    return {"status": "unsubscribed", "kind": kind, "label": label}


@router.delete("/notifications")
async def clear_notifications(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Clear the whole account inbox, including entries beyond its newest 30."""
    return {"removed": await notification_service.dismiss(session, current.id)}


@router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return {
        "removed": await notification_service.dismiss(session, current.id, notification_id)
    }
