"""Share links, share-image teasers and post captions, built from an opportunity's own fields."""

import base64
import hashlib
import hmac
import re
import uuid
from datetime import date

from pydantic import BaseModel

from api.auth import security
from api.core.config import settings
from api.opportunities import models as m

SHORT_LIMIT = 280
FORMATS = ("square", "wide", "story")
_MAC_BYTES = 12
SHAREABLE = ("published", "archived")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,200}$")

_CATEGORY_TAGS = {
    "startup": "#Startups",
    "research": "#Research",
    "student": "#Students",
}
_KIND_TAGS = {
    "grant": "#Grants",
    "fellowship": "#Fellowships",
    "scholarship": "#Scholarships",
    "accelerator": "#Accelerators",
    "incubator": "#Incubators",
    "competition": "#Competitions",
    "internship": "#Internships",
    "call_for_proposals": "#CallForProposals",
    "training": "#Training",
    "conference": "#Conferences",
    "job": "#Jobs",
}


class ShareImages(BaseModel):
    square: str
    wide: str
    story: str


class ShareCaptions(BaseModel):
    short: str
    standard: str
    hashtags: str


class ShareKit(BaseModel):
    share_url: str
    images: ShareImages
    captions: ShareCaptions
    disclaimer: str


class SharedTeaser(BaseModel):
    slug: str
    audience: str
    status: str
    title: str
    organization: str
    category: str
    kind: str
    benefits: str
    deadline: str
    deadline_date: date | None
    rolling: bool
    seed: str


def _key() -> bytes:
    return hashlib.sha256(b"blesser-share:" + security._SIGNING_KEY.encode()).digest()


def _canonical_uuid(value: str) -> bytes | None:
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return None
    return parsed.bytes if str(parsed) == value else None


def make_token(opportunity_id: str, sharer_id: str | None = None) -> str:
    """Stateless, signed (opportunity, sharer); compact when both are UUIDs."""
    opp = _canonical_uuid(opportunity_id)
    sharer = _canonical_uuid(sharer_id) if sharer_id else b""
    if opp is not None and sharer is not None:
        body = b"\x01" + opp + sharer
    else:
        raw = opportunity_id.encode()
        body = b"\x02" + bytes([len(raw)]) + raw + (sharer_id or "").encode()
    mac = hmac.new(_key(), body, hashlib.sha256).digest()[:_MAC_BYTES]
    return base64.urlsafe_b64encode(body + mac).rstrip(b"=").decode()


def read_token(token: str) -> tuple[str, str | None] | None:
    """(opportunity_id, sharer_id) for a genuine token, else None."""
    if not _TOKEN_RE.match(token):
        return None
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except ValueError:
        return None
    body, mac = raw[:-_MAC_BYTES], raw[-_MAC_BYTES:]
    if len(body) < 2:
        return None
    expected = hmac.new(_key(), body, hashlib.sha256).digest()[:_MAC_BYTES]
    if not hmac.compare_digest(mac, expected):
        return None
    if body[0] == 1 and len(body) in (17, 33):
        sharer = str(uuid.UUID(bytes=body[17:])) if len(body) == 33 else None
        return str(uuid.UUID(bytes=body[1:17])), sharer
    if body[0] == 2:
        size = body[1]
        try:
            opp = body[2 : 2 + size].decode()
            sharer = body[2 + size :].decode()
        except UnicodeDecodeError:
            return None
        if len(opp) == size:
            return opp, sharer or None
    return None


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clip(text: str, limit: int) -> str:
    """Cut at a word boundary to at most `limit` characters, ending in an ellipsis."""
    text = _squash(text)
    if len(text) <= limit:
        return text
    if limit < 2:
        return ""
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:.-–—(/") + "…"


def _sentence(text: str) -> str:
    return _squash(text).rstrip(".;: ")


def day(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def deadline_text(opp: m.Opportunity) -> str:
    if opp.status == "archived":
        return "Closed"
    if opp.rolling:
        return "Rolling, apply any time"
    if opp.deadline_date:
        return day(opp.deadline_date)
    return clip(opp.deadline, 60) or "See the official page"


def disclaimer(opp: m.Opportunity) -> str:
    org = _squash(opp.organization)
    return f"Blesser is not affiliated with {org or 'the organization offering it'}."


def hashtags(opp: m.Opportunity) -> list[str]:
    tags = [_KIND_TAGS.get(opp.kind), _CATEGORY_TAGS.get(opp.category), "#Ghana"]
    return list(dict.fromkeys(t for t in tags if t))[:4]


def _first_short_sentence(text: str, limit: int = 160) -> str:
    first = re.split(r"(?<=[.!?])\s", _squash(text), maxsplit=1)[0]
    return first if 0 < len(first) <= limit else ""


def short_caption(opp: m.Opportunity, share_url: str) -> str:
    if opp.status == "archived":
        when = "Now closed"
    elif opp.rolling:
        when = "Apply any time"
    elif opp.deadline_date:
        when = f"Deadline {day(opp.deadline_date)}"
    else:
        when = f"Deadline: {clip(opp.deadline, 40)}" if _squash(opp.deadline) else ""

    def end(text: str) -> str:
        return text if text.endswith("…") else f"{text}."

    def build(title: str, org: str, benefit: str) -> str:
        parts = [f"{title} ({org})." if org else end(title)]
        if benefit:
            parts.append(end(benefit))
        if when:
            parts.append(f"{when}.")
        parts.append(f"{share_url} via Blesser")
        return " ".join(parts)

    title, org = _sentence(opp.title), clip(_sentence(opp.organization), 60)
    benefit = _sentence(opp.benefits.split("\n")[0] if opp.benefits else "")
    text = build(title, org, benefit)
    if len(text) > SHORT_LIMIT and benefit:
        room = SHORT_LIMIT - len(build(title, org, "")) - 2
        benefit = clip(benefit, room) if room >= 24 else ""
        text = build(title, org, benefit)
    if len(text) > SHORT_LIMIT:
        room = SHORT_LIMIT - len(build("", org, benefit))
        title = clip(title, max(room, 24))
        text = build(title, org, benefit)
    if len(text) > SHORT_LIMIT and org:
        room = SHORT_LIMIT - len(build(title, "", benefit)) - 3
        org = clip(org, room) if room >= 12 else ""
        text = build(title, org, benefit)
    return text if len(text) <= SHORT_LIMIT else clip(text, SHORT_LIMIT)


def standard_caption(opp: m.Opportunity, share_url: str) -> str:
    org = _squash(opp.organization)
    lines = [_squash(opp.title)]
    if org:
        lines.append(f"Offered by {org}")
    lines.append("")
    if opp.benefits:
        lines.append(_squash(opp.benefits))
    if eligibility := _first_short_sentence(opp.eligibility):
        lines.append(eligibility)
    lines.append(f"Deadline: {deadline_text(opp)}")
    lines += [
        "",
        f"Details and the official link: {share_url}",
        (
            "Spotted on Blesser, where we gather open opportunities for people in Ghana. "
            f"{disclaimer(opp)[:-1]}; always apply on the official page."
        ),
    ]
    return "\n".join(lines)


def hashtag_caption(opp: m.Opportunity, share_url: str) -> str:
    org = _squash(opp.organization)
    lines = [_squash(opp.title)]
    if org:
        lines.append(f"Offered by {org}")
    lines.append("")
    if opp.benefits:
        lines.append(clip(opp.benefits, 200))
    lines += [
        f"Deadline: {deadline_text(opp)}",
        "",
        share_url,
        f"Spotted on Blesser. {disclaimer(opp)}",
        "",
        " ".join(hashtags(opp)),
    ]
    return "\n".join(lines)


def _site() -> str:
    return settings.site_url.rstrip("/")


def _version(opp: m.Opportunity) -> str:
    stamp = f"{opp.updated_at.isoformat() if opp.updated_at else ''}|{opp.status}"
    return hashlib.sha256(stamp.encode()).hexdigest()[:10]


def kit(opp: m.Opportunity, sharer_id: str | None) -> ShareKit:
    token = make_token(opp.id, sharer_id)
    site = _site()
    if sharer_id is None and opp.audience == "public":
        share_url = f"{site}/opportunities/{opp.slug}"
    else:
        share_url = f"{site}/s/{token}"
    v = _version(opp)
    images = {f: f"{site}/share/{token}/{f}.png?v={v}" for f in FORMATS}
    return ShareKit(
        share_url=share_url,
        images=ShareImages(**images),
        captions=ShareCaptions(
            short=short_caption(opp, share_url),
            standard=standard_caption(opp, share_url),
            hashtags=hashtag_caption(opp, share_url),
        ),
        disclaimer=disclaimer(opp),
    )


def teaser(opp: m.Opportunity) -> SharedTeaser:
    return SharedTeaser(
        slug=opp.slug,
        audience=opp.audience,
        status=opp.status,
        title=_squash(opp.title),
        organization=_squash(opp.organization),
        category=opp.category,
        kind=opp.kind,
        benefits=_squash(opp.benefits),
        deadline=deadline_text(opp),
        deadline_date=opp.deadline_date,
        rolling=bool(opp.rolling),
        seed=opp.slug or opp.id,
    )
