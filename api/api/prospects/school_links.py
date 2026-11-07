"""One school per account, linked to each run that uses it.

``run_schools`` records each run's origin and tier, so per-run caps count
links. A second run finding the same programme reuses it and queues its
own faculty research.
"""

from urllib.parse import urlsplit

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.textnorm import canonical_openalex_id, normalize_text
from api.prospects import models as prospect_models
from api.runs import models as run_models


def url_host(url: str | None) -> str:
    """"https://www.Uni.edu/x" -> "uni.edu"; "" when there is none."""
    raw = (url or "").strip()
    if not raw:
        return ""
    if "//" not in raw:
        raw = "//" + raw
    try:
        host = urlsplit(raw).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.")


def url_page(url: str | None) -> str:
    """Host and path, without scheme, query or a trailing slash."""
    host = url_host(url)
    if not host:
        return ""
    raw = url.strip()
    if "//" not in raw:
        raw = "//" + raw
    try:
        path = urlsplit(raw).path
    except ValueError:
        path = ""
    return host + path.rstrip("/").lower()


async def lock_account(session: AsyncSession, user_id: str) -> None:
    """Held until the transaction ends, so concurrent runs can't both insert one school."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"save_school:{user_id}"},
    )


async def find_school(
    session: AsyncSession,
    user_id: str,
    *,
    name: str,
    website_url: str | None = None,
    institution_id: str | None = None,
) -> prospect_models.School | None:
    """Match by OpenAlex institution id, else normalized name, else website host."""
    schools = (
        (
            await session.execute(
                select(prospect_models.School)
                .where(prospect_models.School.user_id == user_id)
                .order_by(prospect_models.School.id)
            )
        )
        .scalars()
        .all()
    )
    if institution_id:
        wanted = canonical_openalex_id(institution_id)
        for school in schools:
            if school.openalex_institution_id and (
                canonical_openalex_id(school.openalex_institution_id) == wanted
            ):
                return school
    key = normalize_text(name)
    if key:
        for school in schools:
            if normalize_text(school.name) == key:
                return school
    host = url_host(website_url)
    if host:
        for school in schools:
            if url_host(school.website_url) == host:
                return school
    return None


async def find_program(
    session: AsyncSession,
    school_id: str,
    *,
    name: str,
    department_url: str | None = None,
) -> prospect_models.Program | None:
    """Match by normalized name, else department page."""
    programs = (
        (
            await session.execute(
                select(prospect_models.Program)
                .where(prospect_models.Program.school_id == school_id)
                .order_by(prospect_models.Program.id)
            )
        )
        .scalars()
        .all()
    )
    key = normalize_text(name)
    match = next((p for p in programs if normalize_text(p.name) == key), None)
    if match is not None:
        return match
    page = url_page(department_url)
    if page:
        return next((p for p in programs if url_page(p.department_url) == page), None)
    return None


def fill_school(
    school: prospect_models.School,
    *,
    country: str | None = None,
    website_url: str | None = None,
    image_url: str | None = None,
) -> None:
    """Fill in what a reused school lacked; never overwrite."""
    if country and not school.country:
        school.country = country
    if website_url and not school.website_url:
        school.website_url = website_url
    if image_url and not school.image_url:
        school.image_url = image_url


async def run_link(
    session: AsyncSession, run_id: str, school_id: str
) -> prospect_models.RunSchool | None:
    return await session.get(prospect_models.RunSchool, (run_id, school_id))


async def link_school(
    session: AsyncSession,
    run_id: str,
    school: prospect_models.School,
    *,
    origin: str,
    tier: str | None = None,
) -> prospect_models.RunSchool:
    link = await run_link(session, run_id, school.id)
    if link is None:
        link = prospect_models.RunSchool(
            run_id=run_id, school_id=school.id, origin=origin, tier=tier
        )
        session.add(link)
        await session.flush()
    return link


def run_school_ids(run_id: str):
    return select(prospect_models.RunSchool.school_id).where(
        prospect_models.RunSchool.run_id == run_id
    )


async def count_links(
    session: AsyncSession, run_id: str, *, origin: str, tier: str | None = None
) -> int:
    """Schools a run linked with this origin (and tier, when given)."""
    link = prospect_models.RunSchool
    query = (
        select(func.count())
        .select_from(link)
        .where(link.run_id == run_id, link.origin == origin)
    )
    if tier is not None:
        query = query.where(link.tier == tier)
    return (await session.execute(query)).scalar() or 0


async def program_in_run(session: AsyncSession, run_id: str, program_id: str) -> bool:
    """Every way a programme joins a run queues one research_professor task for it."""
    task = run_models.ResearchTask
    found = (
        await session.execute(
            select(task.id)
            .where(
                task.run_id == run_id,
                task.target_id == program_id,
                task.task_type == "research_professor",
            )
            .limit(1)
        )
    ).first()
    return found is not None


async def latest_run_id(session: AsyncSession, school_id: str) -> str | None:
    """Where manual additions at the school are queued."""
    link = prospect_models.RunSchool
    row = (
        await session.execute(
            select(link.run_id)
            .where(link.school_id == school_id)
            .order_by(link.found_at.desc(), link.run_id.desc())
            .limit(1)
        )
    ).first()
    return row[0] if row else None
