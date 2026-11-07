"""Daily jobs from the worker's reaper loop: deadline reminders and the email digest.

Reminders fire 14, 7 and 1 days out for saved/preparing applications, counted in the
owner's timezone from REMINDER_HOUR on. Each fires once per deadline date
(moving the deadline re-arms them); one missed while no worker ran goes out
under the next threshold.
"""

from datetime import date, datetime, timedelta

from sqlalchemy import or_, select

from api.applications import models as application_models
from api.auth import models as auth_models
from api.core import mailer
from api.core.mail_layout import Footer, Item, compose
from api.core.time import utcnow_naive
from api.notifications import models as notification_models
from api.notifications.delivery import app_url, settings_link, unsubscribe_link
from api.notifications.service import DIGEST, local_now, notify

REMINDER_DAYS = (1, 7, 14)
#: Local hour from which a day's reminders and digest go out.
REMINDER_HOUR = 8
#: Statuses that still need the deadline; anything later stops reminders.
OPEN_STATUSES = application_models.OPEN_STATUSES


def threshold_for(days_left: int) -> int | None:
    """Smallest threshold not yet passed; None when past or over 14 days off."""
    if days_left < 0:
        return None
    for threshold in REMINDER_DAYS:
        if days_left <= threshold:
            return threshold
    return None


def _when(days_left: int) -> str:
    if days_left == 0:
        return "today"
    if days_left == 1:
        return "tomorrow"
    return f"in {days_left} days"


async def check_deadlines(session, now: datetime | None = None) -> int:
    """Create due reminders; returns how many were created. Commits."""
    now = now or utcnow_naive()
    today = now.date()
    app = application_models.Application
    prefs_model = notification_models.NotificationPreference
    # A day of slack each side covers every timezone's "today".
    rows = (
        await session.execute(
            select(app, prefs_model)
            .outerjoin(prefs_model, prefs_model.user_id == app.user_id)
            .where(
                app.deadline_date.is_not(None),
                app.status.in_(OPEN_STATUSES),
                app.deadline_date >= today - timedelta(days=1),
                app.deadline_date <= today + timedelta(days=max(REMINDER_DAYS) + 1),
            )
        )
    ).all()
    created = 0
    for application, prefs in rows:
        local = local_now(prefs, now)
        if local.hour < REMINDER_HOUR:
            continue
        days_left = (application.deadline_date - local.date()).days
        threshold = threshold_for(days_left)
        if threshold is None:
            continue
        name = application.title + (f" ({application.organization})" if application.organization else "")
        if await notify(
            session,
            user_id=application.user_id,
            kind="deadline",
            title=f"Application deadline {_when(days_left)}",
            body=f"{name} is due {_when(days_left)} ({application.deadline_date:%d %b %Y}).",
            link=f"/applications/{application.id}",
            entity_id=application.id,
            # The date too: moving a deadline re-arms its reminders.
            dedupe_key=f"app:{application.id}:{threshold}:{application.deadline_date.isoformat()}",
        ):
            created += 1
    await session.commit()
    return created


async def send_digests(session, now: datetime | None = None) -> int:
    """One email a day per opted-in account: unread notifications since the last
    digest (at most a day back) not already emailed. Returns how many. Commits."""
    now = now or utcnow_naive()
    prefs_model = notification_models.NotificationPreference
    n = notification_models.Notification
    rows = (
        await session.execute(
            select(prefs_model, auth_models.User)
            .join(auth_models.User, auth_models.User.id == prefs_model.user_id)
            .where(
                prefs_model.email_digest.is_(True),
                auth_models.User.email_verified_at.is_not(None),
            )
        )
    ).all()
    sent = 0
    for prefs, user in rows:
        local = local_now(prefs, now)
        local_day: date = local.date()
        if local.hour < REMINDER_HOUR or prefs.last_digest_on == local_day:
            continue
        unread = (
            (
                await session.execute(
                    select(n)
                    .where(
                        n.user_id == user.id,
                        n.in_inbox.is_(True),
                        n.read_at.is_(None),
                        n.kind != "test",
                        n.created_at >= now - timedelta(days=1),
                        or_(n.delivery.is_(None), ~n.delivery.contains("email")),
                    )
                    .order_by(n.created_at.desc())
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
        prefs.last_digest_on = local_day
        if not unread:
            continue
        count = f"{len(unread)} unread notification{'s' if len(unread) != 1 else ''}"
        await mailer.send(
            compose(
                to=user.email,
                subject=f"Blesser: {count}",
                eyebrow="Daily digest",
                heading=f"You have {count}",
                paragraphs=["Here is what happened in the last day."],
                items=[Item(row.title, row.body or "", app_url(row.link)) for row in unread],
                action=("Open your inbox", app_url("/")),
                footer=Footer(
                    reason="You're getting this because the daily digest is on in your notification settings.",
                    links=[("Stop the daily digest", unsubscribe_link(user.id, DIGEST)), ("Notification settings", settings_link())],
                ),
            )
        )
        sent += 1
    await session.commit()
    return sent
