"""Notification service: event kinds, preferences, and create-once.

`notify` inserts one row (ON CONFLICT on dedupe_key) inside the caller's
transaction and queues a pg_notify wake, which only fires on commit.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.core.ids import new_id
from api.core.time import utcnow_naive
from api.notifications import models as notification_models
from api.runs.notify import CHANNEL

CHANNELS = ("inbox", "push", "email")


@dataclass(frozen=True)
class Kind:
    label: str
    description: str
    inbox: bool = True
    push: bool = False
    email: bool = False
    #: Listed on the settings page (the test notification is not).
    configurable: bool = True


KINDS: dict[str, Kind] = {
    "run_finished": Kind(
        "Run finished", "A run is done, with its candidate count.", push=True
    ),
    "first_candidate": Kind(
        "First candidate saved", "A run saved its first matching professor."
    ),
    "run_paused": Kind(
        "Run paused",
        "A run stopped because the model allowance ran out.",
        push=True,
    ),
    "run_attention": Kind(
        "Run needs attention", "A task in a run failed after its retries."
    ),
    "drafts_ready": Kind(
        "Email drafts ready", "Drafts you asked for are ready to review.", push=True
    ),
    "deadline": Kind(
        "Application deadlines",
        "Reminders 14, 7 and 1 days before a tracked deadline.",
        push=True,
        email=True,
    ),
    "test": Kind("Test notification", "", push=True, configurable=False),
}

#: Settings-page pseudo-kind for the daily digest's unsubscribe link.
DIGEST = "digest"


def defaults(kind: str) -> dict[str, bool]:
    spec = KINDS.get(kind) or Kind(kind, "")
    return {"inbox": spec.inbox, "push": spec.push, "email": spec.email}


def channels_for(prefs: notification_models.NotificationPreference | None, kind: str) -> dict[str, bool]:
    """Stored overrides on top of the kind's defaults; the test kind ignores preferences."""
    result = defaults(kind)
    if prefs is None or kind == "test":
        return result
    stored = (prefs.channels or {}).get(kind) or {}
    for channel in CHANNELS:
        if isinstance(stored.get(channel), bool):
            result[channel] = stored[channel]
    return result


def zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def valid_zone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def local_now(prefs: notification_models.NotificationPreference | None, now: datetime | None = None) -> datetime:
    """The account's wall clock (UTC until a timezone is known)."""
    now = now or utcnow_naive()
    aware = now.replace(tzinfo=UTC) if now.tzinfo is None else now
    return aware.astimezone(zone(prefs.timezone if prefs else None))


def parse_hhmm(value: str | None) -> time | None:
    if not value:
        return None
    try:
        hours, minutes = value.split(":")
        return time(int(hours), int(minutes))
    except ValueError:
        return None


def in_quiet_hours(prefs: notification_models.NotificationPreference | None, now: datetime | None = None) -> bool:
    """True inside the quiet window in the account's timezone; may span midnight."""
    if prefs is None:
        return False
    start, end = parse_hhmm(prefs.quiet_start), parse_hhmm(prefs.quiet_end)
    if start is None or end is None or start == end:
        return False
    clock = local_now(prefs, now).time().replace(tzinfo=None)
    if start < end:
        return start <= clock < end
    return clock >= start or clock < end


async def get_prefs(session, user_id: str) -> notification_models.NotificationPreference | None:
    return await session.get(notification_models.NotificationPreference, user_id)


async def ensure_prefs(session, user_id: str) -> notification_models.NotificationPreference:
    prefs = await get_prefs(session, user_id)
    if prefs is None:
        prefs = notification_models.NotificationPreference(user_id=user_id, channels={})
        session.add(prefs)
        await session.flush()
    return prefs


async def wake_delivery(session, user_id: str) -> None:
    """Queue a delivery-loop wake (fires on commit) on the run events channel."""
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": CHANNEL, "payload": f"{user_id}:notifications"},
    )


async def notify(
    session,
    *,
    user_id: str,
    kind: str,
    title: str,
    dedupe_key: str,
    body: str = "",
    link: str = "",
    entity_id: str | None = None,
) -> bool:
    """Create one notification unless the dedupe_key exists; True when created.
    Never commits."""
    prefs = await get_prefs(session, user_id)
    channels = channels_for(prefs, kind)
    outbound = channels["push"] or channels["email"]
    now = utcnow_naive()
    stmt = (
        pg_insert(notification_models.Notification)
        .values(
            id=new_id(),
            user_id=user_id,
            kind=kind,
            title=title[:200],
            body=body[:500],
            link=link[:500],
            entity_id=entity_id,
            dedupe_key=dedupe_key[:200],
            in_inbox=channels["inbox"],
            created_at=now,
            # Nothing to send: mark handled so the delivery loop skips it.
            delivered_at=None if outbound else now,
            delivery=None if outbound else "none",
        )
        .on_conflict_do_nothing(constraint="uq_notifications_user_dedupe")
        .returning(notification_models.Notification.id)
    )
    created = (await session.execute(stmt)).scalar_one_or_none() is not None
    if created and outbound:
        await wake_delivery(session, user_id)
    return created


def to_out(row: notification_models.Notification) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "title": row.title,
        "body": row.body,
        "link": row.link,
        "entity_id": row.entity_id,
        "created_at": row.created_at,
        "read_at": row.read_at,
    }


def _inbox(user_id: str):
    return (
        notification_models.Notification.user_id == user_id,
        notification_models.Notification.in_inbox.is_(True),
    )


async def list_inbox(session, user_id: str, limit: int = 30) -> dict:
    rows = (
        (
            await session.execute(
                select(notification_models.Notification)
                .where(*_inbox(user_id))
                .order_by(notification_models.Notification.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    unread = (
        await session.execute(
            select(func.count())
            .select_from(notification_models.Notification)
            .where(*_inbox(user_id), notification_models.Notification.read_at.is_(None))
        )
    ).scalar() or 0
    prefs = await get_prefs(session, user_id)
    return {
        "items": [to_out(r) for r in rows],
        "unread": unread,
        "timezone": prefs.timezone if prefs else None,
    }


async def mark_read(session, user_id: str, notification_id: str | None = None) -> int:
    """Mark one (or, with no id, every) unread notification read."""
    stmt = update(notification_models.Notification).where(
        notification_models.Notification.user_id == user_id,
        notification_models.Notification.read_at.is_(None),
    )
    if notification_id is not None:
        stmt = stmt.where(notification_models.Notification.id == notification_id)
    result = await session.execute(stmt.values(read_at=utcnow_naive()))
    await session.commit()
    return result.rowcount or 0


async def dismiss(session, user_id: str, notification_id: str | None = None) -> int:
    """Remove one or all inbox entries without losing delivery or dedupe history."""
    stmt = update(notification_models.Notification).where(*_inbox(user_id))
    if notification_id is not None:
        stmt = stmt.where(notification_models.Notification.id == notification_id)
    result = await session.execute(stmt.values(in_inbox=False))
    await session.commit()
    return result.rowcount or 0


def prefs_out(prefs: notification_models.NotificationPreference | None) -> dict:
    kinds = []
    for key, spec in KINDS.items():
        if not spec.configurable:
            continue
        kinds.append(
            {
                "kind": key,
                "label": spec.label,
                "description": spec.description,
                "channels": channels_for(prefs, key),
                "defaults": defaults(key),
            }
        )
    return {
        "kinds": kinds,
        "quiet_start": prefs.quiet_start if prefs else None,
        "quiet_end": prefs.quiet_end if prefs else None,
        "timezone": prefs.timezone if prefs else None,
        "email_digest": bool(prefs.email_digest) if prefs else False,
    }


async def update_prefs(session, user_id: str, patch: dict) -> dict:
    """Apply a validated PATCH (see schemas.PreferencesIn)."""
    prefs = await ensure_prefs(session, user_id)
    if "channels" in patch and patch["channels"] is not None:
        merged = {k: dict(v) for k, v in (prefs.channels or {}).items()}
        for kind, channels in patch["channels"].items():
            if kind not in KINDS or not KINDS[kind].configurable:
                continue
            entry = merged.setdefault(kind, {})
            for channel, on in (channels or {}).items():
                if channel in CHANNELS and isinstance(on, bool):
                    entry[channel] = on
        prefs.channels = merged
    for field in ("quiet_start", "quiet_end", "timezone", "email_digest"):
        if field in patch:
            setattr(prefs, field, patch[field])
    await session.commit()
    return prefs_out(prefs)


async def unsubscribe_email(session, user_id: str, kind: str) -> str:
    """Turn off email for one kind (or the digest); returns its label."""
    prefs = await ensure_prefs(session, user_id)
    if kind == DIGEST:
        prefs.email_digest = False
        label = "Daily digest"
    else:
        merged = {k: dict(v) for k, v in (prefs.channels or {}).items()}
        merged.setdefault(kind, {})["email"] = False
        prefs.channels = merged
        label = KINDS[kind].label if kind in KINDS else kind
    await session.commit()
    return label
