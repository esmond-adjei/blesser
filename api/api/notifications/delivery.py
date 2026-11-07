"""Notification delivery: push and email after commit, from the worker.

Rows are claimed FOR UPDATE SKIP LOCKED so workers never double-send. Quiet
hours hold a row; past NOTIFICATION_HOURLY_CAP it is marked "capped" (inbox
only); a 404/410 from a push service deletes that subscription. Email needs a
verified address.
"""

from datetime import datetime, timedelta

from sqlalchemy import delete, func, or_, select

from api.auth import models as auth_models
from api.auth import security as auth_security
from api.core import mailer
from api.core.config import settings
from api.core.mail_layout import Footer, compose
from api.core.time import utcnow_naive
from api.notifications import models as notification_models
from api.notifications import push
from api.notifications.service import KINDS, channels_for, get_prefs, in_quiet_hours

UNSUBSCRIBE_TOKEN = "notif_unsub"
UNSUBSCRIBE_TTL = timedelta(days=90)


def app_url(path: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}{path or '/'}"


def unsubscribe_link(user_id: str, kind: str) -> str:
    token = auth_security.signed_token(
        UNSUBSCRIBE_TOKEN, {"sub": user_id, "kind": kind}, UNSUBSCRIBE_TTL
    )
    return app_url(f"/notifications/unsubscribe?token={token}")


def read_unsubscribe(token: str) -> tuple[str, str] | None:
    claims = auth_security.read_signed(UNSUBSCRIBE_TOKEN, token or "")
    if not claims or not isinstance(claims.get("sub"), str) or not isinstance(claims.get("kind"), str):
        return None
    return claims["sub"], claims["kind"]


def settings_link() -> str:
    return app_url("/new?settings=notifications")


def email_for(user: auth_models.User, notification: notification_models.Notification) -> mailer.Mail:
    kind = KINDS.get(notification.kind)
    return compose(
        to=user.email,
        subject=notification.title,
        eyebrow=kind.label if kind else None,
        heading=notification.title,
        paragraphs=[notification.body] if notification.body else [],
        action=("Open in Graduator", app_url(notification.link)),
        footer=Footer(
            reason=f"You're getting this because email is on for {kind.label if kind else 'this event'} in your notification settings.",
            links=[("Stop emails like this one", unsubscribe_link(user.id, notification.kind)), ("Notification settings", settings_link())],
        ),
    )


async def _sent_last_hour(session, user_id: str, now: datetime) -> int:
    n = notification_models.Notification
    return (
        await session.execute(
            select(func.count())
            .select_from(n)
            .where(
                n.user_id == user_id,
                n.delivered_at >= now - timedelta(hours=1),
                or_(n.delivery.contains("push"), n.delivery.contains("email")),
            )
        )
    ).scalar() or 0


async def push_to_user(session, notification: notification_models.Notification, now: datetime) -> int:
    """Push to every device of the owner; returns how many accepted. 404/410 subs are deleted."""
    if not push.push_configured():
        push.warn_unconfigured()
        return 0
    subs = (
        (
            await session.execute(
                select(notification_models.PushSubscription).where(
                    notification_models.PushSubscription.user_id == notification.user_id
                )
            )
        )
        .scalars()
        .all()
    )
    payload = push.payload_for(notification)
    sent = 0
    for sub in subs:
        status = await push.send_web_push(sub.endpoint, sub.p256dh, sub.auth, payload)
        if 200 <= status < 300:
            sub.last_ok_at = now
            sent += 1
        elif status in push.GONE_STATUSES:
            await session.execute(
                delete(notification_models.PushSubscription).where(
                    notification_models.PushSubscription.id == sub.id
                )
            )
            print(f"[notifications] removed expired push subscription {sub.id[:8]}", flush=True)
    return sent


async def deliver_one(
    session,
    notification: notification_models.Notification,
    now: datetime | None = None,
) -> bool:
    """Deliver one row. Returns False when it must wait (quiet hours)."""
    now = now or utcnow_naive()
    prefs = await get_prefs(session, notification.user_id)
    channels = channels_for(prefs, notification.kind)
    if not (channels["push"] or channels["email"]):
        notification.delivered_at, notification.delivery = now, "none"
        return True
    if in_quiet_hours(prefs, now):
        return False
    if await _sent_last_hour(session, notification.user_id, now) >= max(
        settings.notification_hourly_cap, 0
    ):
        notification.delivered_at, notification.delivery = now, "capped"
        print(f"[notifications] hourly cap reached for {notification.user_id[:8]}; inbox only", flush=True)
        return True
    sent: list[str] = []
    if channels["push"] and await push_to_user(session, notification, now):
        sent.append("push")
    if channels["email"]:
        user = await session.get(auth_models.User, notification.user_id)
        # Only to proven addresses: an unverified sign-up must not mail someone else.
        verified = user is not None and user.email_verified_at is not None
        if verified and await mailer.send(email_for(user, notification)):
            sent.append("email")
    notification.delivered_at = now
    notification.delivery = ",".join(sent) or "none"
    return True


async def deliver_pending(session, limit: int = 200, now: datetime | None = None) -> int:
    """One delivery pass; returns rows handled. Quiet-hours rows stay pending."""
    now = now or utcnow_naive()
    rows = (
        (
            await session.execute(
                select(notification_models.Notification)
                .where(notification_models.Notification.delivered_at.is_(None))
                .order_by(notification_models.Notification.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    handled = 0
    for row in rows:
        if await deliver_one(session, row, now):
            handled += 1
    await session.commit()
    return handled
