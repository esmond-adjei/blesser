"""Transactional mail over standard SMTP (any provider) or a `console` backend for dev/tests."""

import asyncio
import logging
import smtplib
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from api.core.config import settings

log = logging.getLogger(__name__)

LOGO_CID = "blesser-logo"
_LOGO = Path(__file__).with_name("mail_logo.png")


@dataclass
class Mail:
    to: str
    subject: str
    text: str
    html: str | None = None


# Messages "sent" by the console backend, newest last (tests read this).
outbox: list[Mail] = []


def build_message(mail: Mail) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = mail.to
    msg["Subject"] = mail.subject
    msg.set_content(mail.text)
    if mail.html:
        msg.add_alternative(mail.html, subtype="html")
        # Inline, not hosted: clients block remote images and dev URLs aren't reachable.
        if f"cid:{LOGO_CID}" in mail.html:
            msg.get_payload()[1].add_related(_LOGO.read_bytes(), "image", "png", cid=f"<{LOGO_CID}>")
    return msg


def _send_smtp(mail: Mail) -> None:
    msg = build_message(mail)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)


async def send(mail: Mail) -> bool:
    """Deliver one message. Never raises: auth flows must not leak or fail on delivery."""
    if settings.mail_backend == "smtp":
        try:
            await asyncio.to_thread(_send_smtp, mail)
            return True
        except Exception as exc:  # noqa: BLE001 - logged, never surfaced
            log.error("mail delivery failed to %s: %s", mail.to, exc)
            return False
    outbox.append(mail)
    del outbox[:-50]
    # stderr, not logging: uvicorn hides INFO from app loggers, and in dev these
    # links are the whole point.
    print(f"[mail:console] to={mail.to} subject={mail.subject}\n{mail.text}\n", file=sys.stderr, flush=True)
    return True
