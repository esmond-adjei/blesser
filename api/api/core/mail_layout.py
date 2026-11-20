"""The branded email layout: one table-based HTML shell plus a matching plain-text part.

Email clients ignore external stylesheets and most modern CSS, so every style is
inline and layout is tables. The one <style> block only adds what inline styles
cannot: web fonts for clients that load them, and phone-width padding. Colours,
radii and type come from design-system/tokens.json through mail_tokens.py.
"""

from dataclasses import dataclass, field
from html import escape

from api.core import mail_tokens as t
from api.core.mailer import LOGO_CID, Mail

# The logo image is the full lockup (Sunrise mark and "blesser"), drawn at 2x.
LOGO_WIDTH, LOGO_HEIGHT = 119, 32
TAGLINE = "Blesser helps you find grants, fellowships, scholarships and accelerators in Ghana, and see them through to a yes."
SANS = t.FONT_SANS
DISPLAY = t.FONT_DISPLAY


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
    if items:
        parts.append(
            "\n\n".join(
                "\n".join(x for x in (f"- {item.title}", f"  {item.body}" if item.body else "", f"  {item.link}" if item.link else "") if x)
                for item in items
            )
        )
    if action:
        parts.append(f"{action[0]}: {action[1]}")
    if note:
        parts.append(note)
    out = "\n\n".join(parts)
    out += "\n\n--\n"
    if footer:
        out += footer.reason + "\n" + "".join(f"{label}: {url}\n" for label, url in footer.links)
    else:
        out += TAGLINE + "\n"
    return out


def _p(text: str, style: str, margin: str = "0 0 16px") -> str:
    return f'<p style="margin:{margin};{style}">{escape(text)}</p>'


def _eyebrow(label: str) -> str:
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 16px">'
        f'<tr><td bgcolor="{t.SUN_SOFT}" style="background:{t.SUN_SOFT};border-radius:{t.RADIUS_FULL};padding:4px 12px;'
        f'font-family:{SANS};font-size:12px;font-weight:600;line-height:16px;letter-spacing:0.02em;color:{t.SUN_INK}">'
        f"{escape(label)}</td></tr></table>"
    )


def _button(label: str, url: str) -> str:
    # Pill, sun fill, on-sun text: the one primary action. The <a> carries the
    # padding so the whole pill is clickable; Outlook falls back to a square fill.
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 20px">'
        f'<tr><td bgcolor="{t.SUN}" style="background:{t.SUN};border-radius:{t.RADIUS_FULL}">'
        f'<a href="{escape(url)}" style="display:inline-block;padding:14px 28px;font-family:{SANS};font-size:16px;'
        f'font-weight:600;line-height:20px;color:{t.ON_SUN};text-decoration:none;border-radius:{t.RADIUS_FULL}">{escape(label)}</a>'
        "</td></tr></table>"
    )


def _items(items: list[Item]) -> str:
    rows = []
    for i, item in enumerate(items):
        border = f"border-top:1px solid {t.SEPARATOR};" if i else ""
        title = escape(item.title)
        if item.link:
            title = f'<a href="{escape(item.link)}" style="color:{t.INK};text-decoration:none">{title}</a>'
        body = (
            f'<div style="margin-top:2px;font-size:14px;line-height:20px;color:{t.INK_SECONDARY}">{escape(item.body)}</div>'
            if item.body
            else ""
        )
        arrow = (
            f'<td width="24" align="right" valign="top" style="{border}padding:14px 0;font-family:{SANS};font-size:16px;line-height:22px">'
            f'<a href="{escape(item.link)}" style="color:{t.LINK};text-decoration:none" aria-hidden="true">&rarr;</a></td>'
            if item.link
            else f'<td width="24" style="{border}"></td>'
        )
        rows.append(
            f'<tr><td style="{border}padding:14px 0;font-family:{SANS}">'
            f'<div style="font-size:16px;font-weight:600;line-height:22px;color:{t.INK}">{title}</div>{body}</td>{arrow}</tr>'
        )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{t.SURFACE_SUNK}" '
        f'style="background:{t.SURFACE_SUNK};border-radius:{t.RADIUS_MD};margin:4px 0 24px">'
        f'<tr><td style="padding:4px 20px">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{"".join(rows)}</table>'
        "</td></tr></table>"
    )


def _html(subject, heading, paragraphs, action, items, eyebrow, note, footer) -> str:
    body = _eyebrow(eyebrow) if eyebrow else ""
    body += (
        f'<h1 style="margin:0 0 12px;font-family:{DISPLAY};font-size:26px;font-weight:700;line-height:32px;'
        f'letter-spacing:-0.015em;color:{t.INK}">{escape(heading)}</h1>'
    )
    body += "".join(_p(p, f"font-size:16px;line-height:24px;color:{t.INK_SECONDARY}") for p in paragraphs)
    if items:
        body += _items(items)
    if action:
        body += _button(*action)
        body += _p(
            "If the button does not work, paste this link into your browser:",
            f"font-size:13px;line-height:18px;color:{t.INK_TERTIARY}",
            "0 0 4px",
        )
        body += (
            f'<p style="margin:0;font-size:13px;line-height:18px;word-break:break-all">'
            f'<a href="{escape(action[1])}" style="color:{t.LINK};text-decoration:underline">{escape(action[1])}</a></p>'
        )
    if note:
        body += (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:24px">'
            f'<tr><td style="border-top:1px solid {t.SEPARATOR};padding-top:20px;font-family:{SANS};font-size:13px;'
            f'line-height:20px;color:{t.INK_TERTIARY}">{escape(note)}</td></tr></table>'
        )

    link_style = f"color:{t.INK_SECONDARY};text-decoration:underline"
    foot = f'<p style="margin:0 0 8px">{escape(footer.reason if footer else TAGLINE)}</p>'
    if footer and footer.links:
        links = "&nbsp;&nbsp;&nbsp;".join(
            f'<a href="{escape(url)}" style="{link_style}">{escape(label)}</a>' for label, url in footer.links
        )
        foot += f'<p style="margin:0">{links}</p>'

    preheader = escape(paragraphs[0] if paragraphs else heading)
    # Padding after the preheader keeps clients from pulling body text into the preview line.
    spacer = "&#847;&zwnj;&nbsp;" * 60

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light"><title>{escape(subject)}</title>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700&amp;family=Figtree:wght@400;600;800&amp;display=swap" rel="stylesheet">
<style>
body,table,td,a{{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}}
a[x-apple-data-detectors]{{color:inherit!important;text-decoration:none!important}}
@media (max-width:600px){{.bl-outer{{padding:20px 12px!important}}.bl-card{{padding:28px 20px!important}}}}
</style></head>
<body style="margin:0;padding:0;background:{t.SURFACE_SUNK}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all">{preheader}{spacer}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{t.SURFACE_SUNK}" style="background:{t.SURFACE_SUNK}">
<tr><td align="center" class="bl-outer" style="padding:40px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px">
<tr><td style="padding:0 4px 20px">
<img src="cid:{LOGO_CID}" width="{LOGO_WIDTH}" height="{LOGO_HEIGHT}" alt="Blesser" style="display:block;border:0;outline:none;text-decoration:none">
</td></tr>
<tr><td bgcolor="{t.SURFACE}" class="bl-card" style="background:{t.SURFACE};border:1px solid {t.SEPARATOR};border-radius:{t.RADIUS_LG};padding:40px;font-family:{SANS};color:{t.INK}">
{body}
</td></tr>
<tr><td style="padding:24px 4px 0;font-family:{SANS};font-size:12px;line-height:18px;color:{t.INK_TERTIARY}">{foot}</td></tr>
</table>
</td></tr></table>
</body></html>"""
