"""Minimal RFC 5545 writer for all-day events: deadlines and due to-dos.

All-day events (DTSTART;VALUE=DATE) sidestep timezones: a deadline is a day,
wherever the reader is. Text is escaped and lines folded at 75 octets.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

PRODID = "-//Blesser//Opportunities//EN"


@dataclass
class Event:
    uid: str
    day: date
    summary: str
    description: str = ""
    url: str = ""
    categories: list[str] = field(default_factory=list)
    # Reminders this many days before; an empty tuple means none.
    alarm_days: tuple[int, ...] = (7, 1)


def escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def fold(line: str) -> str:
    """Fold a content line to 75 octets, never splitting a UTF-8 character."""
    out: list[str] = []
    current = ""
    size = 0
    limit = 75
    for ch in line:
        width = len(ch.encode("utf-8"))
        if size + width > limit:
            out.append(current)
            current, size, limit = " ", 1, 75
        current += ch
        size += width
    out.append(current)
    return "\r\n".join(out)


def _stamp(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%SZ")


def render(events: list[Event], *, name: str, now: datetime) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape(name)}",
        # Hint to subscribing clients: refresh about every six hours.
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    for ev in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev.uid}",
            f"DTSTAMP:{_stamp(now)}",
            f"DTSTART;VALUE=DATE:{ev.day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(ev.day + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{escape(ev.summary)}",
            "TRANSP:TRANSPARENT",
        ]
        if ev.description:
            lines.append(f"DESCRIPTION:{escape(ev.description)}")
        if ev.url:
            lines.append(f"URL:{ev.url}")
        if ev.categories:
            lines.append("CATEGORIES:" + ",".join(escape(c) for c in ev.categories))
        for days in ev.alarm_days:
            if days <= 0:
                continue
            lines += [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{escape(ev.summary)}",
                f"TRIGGER:-P{days}D",
                "END:VALARM",
            ]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"
