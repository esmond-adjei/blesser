"""Candidate PDF exports: gather dossiers, fetch portraits safely, render."""

from __future__ import annotations

import asyncio
import io
import logging
import re
from datetime import UTC, datetime

import httpx
from PIL import Image

from api.applications import service as application_service
from api.auth import models as auth_models
from api.candidates import service as candidate_service
from api.core import egress
from api.core.exceptions import BadRequestError
from api.exports import pdf
from api.outreach import service as outreach_service
from api.prospects import service as prospect_service
from api.runs import models as run_models

log = logging.getLogger(__name__)

#: Most candidates in one PDF; more is a background job, not a request.
MAX_CANDIDATES = 100
#: Portrait fetch limits: a remote photo never stalls or bloats an export.
PHOTO_MAX_BYTES = 3_000_000
PHOTO_TIMEOUT = 4.0
PHOTO_SIDE = 320
#: Decoded size limit: a small compressed file can still unpack huge.
PHOTO_MAX_PIXELS = 25_000_000


async def export_candidates(session, user_id: str, candidate_ids: list[str]) -> tuple[bytes, str]:
    """(PDF bytes, file name); every id must be one of the account's candidates."""
    ids = list(dict.fromkeys(i for i in candidate_ids if i))
    if not ids:
        raise BadRequestError("Pick at least one candidate to export.")
    if len(ids) > MAX_CANDIDATES:
        raise BadRequestError(f"Export at most {MAX_CANDIDATES} candidates at a time.")

    applications = await application_service.list_applications(session, user_id)
    dossiers: list[pdf.Dossier] = []
    photo_urls: list[str | None] = []
    run_titles: dict[str, str] = {}
    for cid in ids:
        c = await candidate_service.get_candidate_detail(session, user_id, cid)
        prof = await prospect_service.get_professor(session, user_id, c["professor_id"])
        drafts = await outreach_service.list_candidate_drafts(session, user_id, cid)
        if c["run_id"] not in run_titles:
            run_titles[c["run_id"]] = await _run_title(session, c["run_id"])
        links: list[tuple[str, str]] = []
        if prof.get("profile_url"):
            links.append(("Faculty profile", prof["profile_url"]))
        if prof.get("openalex_id"):
            oa = prof["openalex_id"]
            links.append(("OpenAlex", oa if oa.startswith("http") else f"https://openalex.org/{oa}"))
        for s in prof.get("socials") or []:
            if isinstance(s, dict) and s.get("url"):
                links.append((s.get("label") or "Link", s["url"]))
        latest = drafts[0] if drafts else None
        dossiers.append(
            pdf.Dossier(
                id=c["id"],
                name=c["professor_name"],
                school=c["school_name"],
                program=c["program_name"],
                status=_status(c["status"]),
                score=c["similarity_score"],
                run_title=run_titles[c["run_id"]],
                rationale=c["rationale"] or "",
                lab=prof.get("lab_name"),
                bio=prof.get("bio"),
                bio_source=prof.get("bio_source"),
                email=prof.get("email"),
                links=links,
                papers=c["papers"],
                draft_subject=latest["subject"] if latest else None,
                draft_body=latest["body"] if latest else None,
                applications=[a for a in applications if _links_candidate(a, cid)],
            )
        )
        photo_urls.append(prof.get("photo_url"))

    photos = await asyncio.gather(*(fetch_photo(u) for u in photo_urls))
    for dossier, photo in zip(dossiers, photos, strict=True):
        dossier.photo = photo
    dossiers.sort(key=lambda d: -1 if d.score is None else d.score, reverse=True)

    user = await session.get(auth_models.User, user_id)
    owner = (user.display_name or user.email) if user is not None else "you"
    now = datetime.now(UTC)
    runs = sorted({d.run_title for d in dossiers if d.run_title})
    several = len(dossiers) > 1
    title = "Candidate dossier" if several else dossiers[0].name
    subtitle = (
        f"{len(dossiers)} professors" + (f" · {runs[0]}" if len(runs) == 1 else f" · {len(runs)} runs" if runs else "")
        if several
        else f"{dossiers[0].school} · {dossiers[0].program}"
    )
    # Synchronous and CPU-bound (two passes): keep it off the event loop.
    body = await asyncio.to_thread(
        pdf.build_pdf,
        dossiers,
        title=title,
        subtitle=subtitle,
        prepared=pdf.prepared_line(owner, now),
    )
    name = (
        f"graduator-dossier-{now:%Y-%m-%d}.pdf"
        if several
        else f"graduator-{_slug(dossiers[0].name) or 'candidate'}.pdf"
    )
    return body, name


def _status(value) -> str:
    return getattr(value, "value", value) or ""


def _links_candidate(app: dict, candidate_id: str) -> bool:
    return any(
        isinstance(p, dict) and p.get("candidate_id") == candidate_id
        for p in app.get("professors") or []
    )


async def _run_title(session, run_id: str) -> str:
    run = await session.get(run_models.Run, run_id)
    if run is None:
        return ""
    parts = [p for p in (run.field, run.region) if p and p != "(preselected list)"]
    return " · ".join(parts)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


async def fetch_photo(url: str | None) -> bytes | None:
    """A small square JPEG portrait, or None. Fetched through the egress guard,
    capped in size and time."""
    if not url or not url.lower().startswith(("https://", "http://")):
        return None
    try:
        async with httpx.AsyncClient(
            transport=egress.GuardedTransport(),
            timeout=PHOTO_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Graduator/1.0 (dossier export)"},
        ) as client, client.stream("GET", url) as resp:
            if resp.status_code != 200:
                return None
            body = bytearray()
            async for chunk in resp.aiter_bytes():
                body.extend(chunk)
                if len(body) > PHOTO_MAX_BYTES:
                    return None
        return await asyncio.to_thread(_square_jpeg, bytes(body))
    except Exception as exc:  # noqa: BLE001 - a photo never fails an export
        log.info("dossier photo skipped (%s): %s", url, egress.public_error(exc))
        return None


def _square_jpeg(data: bytes) -> bytes | None:
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.width * im.height > PHOTO_MAX_PIXELS:
                return None
            im.draft("RGB", (PHOTO_SIDE * 2, PHOTO_SIDE * 2))
            im = im.convert("RGB")
            side = min(im.size)
            left = (im.width - side) // 2
            # Portraits put the face high: crop from the top third.
            top = max(0, min((im.height - side) // 3, im.height - side))
            im = im.crop((left, top, left + side, top + side)).resize((PHOTO_SIDE, PHOTO_SIDE))
            out = io.BytesIO()
            im.save(out, "JPEG", quality=85)
            return out.getvalue()
    except Exception:  # noqa: BLE001 - not an image we can read
        return None
