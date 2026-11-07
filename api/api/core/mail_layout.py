"""The branded email layout: one table-based HTML shell plus a matching plain-text part.

Email clients ignore stylesheets and most modern CSS, so every style is inline and
layout is tables. Colours and type come from docs/design-system/tokens (light theme).
"""

from dataclasses import dataclass, field
from html import escape

from api.core.mailer import LOGO_CID, Mail

CANVAS = "#f5f6f8"
SURFACE = "#ffffff"
SEPARATOR = "#dfe4ea"
LABEL = "#0b1a2e"
LABEL_SECONDARY = "#4a5668"
LABEL_TERTIARY = "#5f6b7c"
TINT = "#1f57b8"
FONT = "'Instrument Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"


@dataclass
class Item:
    title: str
    body: str = ""
    link: str | None = None


@dataclass
class Footer:
    reason: str
    links: list[tuple[str, str]] = field(default_factory=list)


def compose(
    *,
    to: str,
    subject: str,
    heading: str,
    paragraphs: list[str],
    action: tuple[str, str] | None = None,
    items: list[Item] | None = None,
    eyebrow: str | None = None,
    note: str | None = None,
    footer: Footer | None = None,
) -> Mail:
    return Mail(
        to=to,
        subject=subject,
        text=_text(heading, paragraphs, action, items or [], note, footer),
        html=_html(subject, heading, paragraphs, action, items or [], eyebrow, note, footer),
    )


def _text(heading, paragraphs, action, items, note, footer) -> str:
    parts = [heading, *paragraphs]
    if action:
        parts.append(f"{action[0]}: {action[1]}")
    for item in items:
        parts.append("\n".join(x for x in (f"- {item.title}", f"  {item.body}" if item.body else "", f"  {item.link}" if item.link else "") if x))
    if note:
        parts.append(note)
    out = "\n\n".join(parts)
    if footer:
        out += "\n\n--\n" + footer.reason + "\n" + "".join(f"{label}: {url}\n" for label, url in footer.links)
    return out + ("" if out.endswith("\n") else "\n")


def _p(text: str, style: str) -> str:
    return f'<p style="margin:0 0 16px;{style}">{escape(text)}</p>'


def _button(label: str, url: str) -> str:
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 24px">'
        f'<tr><td bgcolor="{TINT}" style="border-radius:8px">'
        f'<a href="{escape(url)}" style="display:inline-block;padding:12px 22px;font-family:{FONT};font-size:15px;'
        f'font-weight:600;line-height:20px;color:#ffffff;text-decoration:none;border-radius:8px">{escape(label)}</a>'
        "</td></tr></table>"
    )


def _items(items: list[Item]) -> str:
    rows = []
    for i, item in enumerate(items):
        border = f"border-top:1px solid {SEPARATOR};" if i else ""
        title = escape(item.title)
        if item.link:
            title = f'<a href="{escape(item.link)}" style="color:{LABEL};text-decoration:none">{title}</a>'
        body = f'<div style="margin-top:2px;font-size:14px;line-height:20px;color:{LABEL_SECONDARY}">{escape(item.body)}</div>' if item.body else ""
        rows.append(f'<tr><td style="{border}padding:12px 0;font-family:{FONT}"><div style="font-size:15px;font-weight:600;line-height:22px">{title}</div>{body}</td></tr>')
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 20px">{"".join(rows)}</table>'


def _html(subject, heading, paragraphs, action, items, eyebrow, note, footer) -> str:
    body = ""
    if eyebrow:
        body += f'<p style="margin:0 0 6px;font-size:13px;font-weight:600;line-height:18px;color:{LABEL_TERTIARY}">{escape(eyebrow)}</p>'
    body += f'<h1 style="margin:0 0 14px;font-size:22px;font-weight:600;line-height:28px;letter-spacing:-0.01em;color:{LABEL}">{escape(heading)}</h1>'
    body += "".join(_p(p, f"font-size:15px;line-height:24px;color:{LABEL_SECONDARY}") for p in paragraphs)
    if items:
        body += _items(items)
    if action:
        body += _button(*action)
        body += _p(f"Or paste this link into your browser: {action[1]}", f"font-size:12px;line-height:18px;color:{LABEL_TERTIARY};word-break:break-all")
    if note:
        body += _p(note, f"font-size:13px;line-height:20px;color:{LABEL_TERTIARY}")

    foot = ""
    if footer:
        links = " &nbsp;·&nbsp; ".join(f'<a href="{escape(url)}" style="color:{LABEL_TERTIARY};text-decoration:underline">{escape(label)}</a>' for label, url in footer.links)
        foot = f'{escape(footer.reason)}{"<br>" + links if links else ""}'

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light"><title>{escape(subject)}</title></head>
<body style="margin:0;padding:0;background:{CANVAS}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{escape(paragraphs[0] if paragraphs else heading)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{CANVAS}" style="background:{CANVAS}">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px">
<tr><td style="padding:0 4px 16px;font-family:{FONT}">
<img src="cid:{LOGO_CID}" width="32" height="32" alt="" style="vertical-align:middle;border:0">
<span style="vertical-align:middle;margin-left:8px;font-size:17px;font-weight:600;letter-spacing:-0.01em;color:{LABEL}">Blesser</span>
</td></tr>
<tr><td bgcolor="{SURFACE}" style="background:{SURFACE};border:1px solid {SEPARATOR};border-radius:12px;padding:32px;font-family:{FONT}">
{body}
</td></tr>
<tr><td style="padding:16px 4px 0;font-family:{FONT};font-size:12px;line-height:18px;color:{LABEL_TERTIARY}">{foot}</td></tr>
</table>
</td></tr></table>
</body></html>"""
