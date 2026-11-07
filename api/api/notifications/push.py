"""Web Push sending (VAPID), behind one function tests can stub.

Returns the push service's HTTP status (0 when unanswered). A no-op while the
VAPID keys are unset; pywebpush is imported lazily.
"""

import asyncio
import json
import logging
from email.utils import parseaddr

from api.core.config import settings

log = logging.getLogger(__name__)

#: Push services answer these when the subscription is gone for good.
GONE_STATUSES = (404, 410)
#: How long the push service keeps an undelivered message (seconds).
PUSH_TTL = 24 * 3600

_warned = False


def push_configured() -> bool:
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def warn_unconfigured() -> None:
    global _warned
    if not _warned:
        _warned = True
        print(
            "[notifications] VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY unset: browser "
            "push is off (inbox and email still deliver)",
            flush=True,
        )


def vapid_subject() -> str:
    if settings.vapid_subject:
        return settings.vapid_subject
    address = parseaddr(settings.mail_from)[1]
    return f"mailto:{address or 'no-reply@localhost'}"


def payload_for(notification) -> dict:
    return {
        "id": notification.id,
        "kind": notification.kind,
        "title": notification.title,
        "body": notification.body,
        "link": notification.link or "/",
    }


def _send_sync(endpoint: str, p256dh: str, auth: str, data: str) -> int:
    from pywebpush import WebPushException, webpush

    try:
        response = webpush(
            subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
            data=data,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": vapid_subject()},
            ttl=PUSH_TTL,
            timeout=10,
        )
        return getattr(response, "status_code", 201)
    except WebPushException as exc:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", 0) or 0
        log.warning("web push failed (%s): %s", status, exc)
        return status


async def send_web_push(endpoint: str, p256dh: str, auth: str, payload: dict) -> int:
    """Encrypt and send one push. Never raises."""
    try:
        return await asyncio.to_thread(_send_sync, endpoint, p256dh, auth, json.dumps(payload))
    except Exception as exc:  # noqa: BLE001 - a broken push must not stop delivery
        log.warning("web push error: %s", exc)
        return 0
