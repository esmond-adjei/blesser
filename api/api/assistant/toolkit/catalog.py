from datetime import date
from typing import Annotated

from pydantic import Field, StringConstraints
from sqlalchemy import select

from api import web
from api.applicant_kit.schemas import http_url
from api.core.exceptions import NotFoundError
from api.core.time import human_day
from api.opportunities import service as opportunities
from api.opportunities.models import OpportunityCategory, OpportunityKind
from api.opportunities.schemas import OpportunitySubmit

from .base import (
    Applied,
    Proposal,
    Query,
    RequiredQuery,
    Tool,
    ToolInput,
    field_lines,
    preview,
    record,
)

OPPORTUNITY_FIELDS = (
    "id",
    "slug",
    "title",
    "organization",
    "summary",
    "category",
    "kind",
    "eligibility",
    "benefits",
    "location",
    "countries",
    "requirements",
    "is_open",
)


class CatalogSearch(ToolInput):
    query: Query = ""
    category: OpportunityCategory | None = None
    kind: OpportunityKind | None = None
    country: Query | None = None
    include_closed: bool = False
    closing_within: int | None = Field(default=None, ge=0, le=365)


class ForYou(ToolInput):
    category: OpportunityCategory | None = None
    kind: OpportunityKind | None = None
    closing_within: int | None = Field(default=None, ge=0, le=365)


class OpportunityLookup(ToolInput):
    opportunity_id: RequiredQuery


class WebSearch(ToolInput):
    query: RequiredQuery


Line = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


class SubmitOpportunity(ToolInput):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)
    ]
    link: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=8, max_length=2000)
    ]
    category: OpportunityCategory
    kind: OpportunityKind = OpportunityKind.other
    organization: Annotated[str, StringConstraints(max_length=200)] = ""
    summary: Annotated[str, StringConstraints(max_length=4000)] = ""
    eligibility: Annotated[str, StringConstraints(max_length=4000)] = ""
    benefits: Line = ""
    location: Annotated[str, StringConstraints(max_length=200)] = ""
    countries: list[Annotated[str, StringConstraints(max_length=80)]] = Field(
        default_factory=list, max_length=20
    )
    deadline_date: date | None = None
    rolling: bool = False


def opportunity(registry, row):
    key = registry.register("opportunity", row, detail=row["organization"])
    return {
        **record(row, OPPORTUNITY_FIELDS),
        "source": key,
        "deadline": registry.deadlines.get(key),
    }


async def _search(session, user_id, args, registry, *, match=None):
    page = await opportunities.list_public(
        session,
        q=getattr(args, "query", ""),
        category=args.category,
        kind=args.kind,
        country=getattr(args, "country", None),
        open_only=not getattr(args, "include_closed", False),
        closing_within=args.closing_within,
        sort="for_you" if match is not None else "relevance",
        limit=12,
        match=match,
    )
    page["items"] = [opportunity(registry, row) for row in page["items"]]
    page["returned"] = len(page["items"])
    page["truncated"] = page["total"] > len(page["items"])
    return page


async def search_catalog(session, user_id, args, registry):
    page = await _search(session, user_id, args, registry)
    page["scope"] = (
        "Published catalog records only, not saved applications or unpublished records."
    )
    if not page["items"]:
        page["message"] = (
            "No published records matched these filters. This does not mean the member has no matching saved application. Use list_applications or get_application for their saved details."
        )
    return page, page["total"]


async def list_for_you(session, user_id, args, registry):
    from api.matching import service as matching

    page = await _search(
        session,
        user_id,
        args,
        registry,
        match=await matching.get_prefs(session, user_id),
    )
    page["scope"] = (
        "Open published listings ordered by the member's match profile, best fit first."
    )
    return page, page["total"]


async def get_opportunity(session, user_id, args, registry):
    row = opportunities.to_out(
        await opportunities.get_or_404(session, args.opportunity_id)
    )
    return opportunity(registry, row), None


async def search_web(session, user_id, args, registry):
    records = []
    for row in web.brief_results(await web.search_web(args.query)):
        url = str(row.get("url") or "")
        try:
            if not http_url(url):
                continue
        except ValueError:
            continue
        title = str(row.get("title") or "Web result")
        key = registry.register("web", {"id": url, "title": title}, url=url)
        records.append(
            {"title": title, "snippet": row.get("snippet", ""), "source": key}
        )
    return {"items": records, "total": len(records)}, len(records)


async def trackable(session, user_id, opportunity_id):
    """A published listing, or one of this member's own scan finds still in review."""
    try:
        return await opportunities.get_or_404(session, opportunity_id)
    except NotFoundError:
        opp = await opportunities.get_or_404(session, opportunity_id, public=False)
        if opp.status == "in_review" and opp.scan_id:
            from api.scans.models import Scan

            owner = await session.scalar(
                select(Scan.user_id).where(Scan.id == opp.scan_id)
            )
            if owner == user_id:
                return opp
        raise


async def propose_track(session, user_id, args):
    opp = await trackable(session, user_id, args.opportunity_id)
    return Proposal(
        f"Track {opp.title} in your applications?", {"opportunity_id": opp.id}
    )


async def apply_track(session, user_id, arguments):
    app, created = await opportunities.track(
        session, user_id, arguments["opportunity_id"]
    )
    due = app["deadline_date"]
    detail = ", ".join(
        part for part in (app["organization"], due and f"Due {human_day(due)}") if part
    )
    return Applied(
        {
            "application_id": app["id"],
            "title": app["title"],
            "already_tracked": not created,
        },
        "Saved to your applications."
        if created
        else "You were already tracking this one.",
        preview("application", app["id"], app["title"], detail),
    )


async def propose_submit(session, user_id, args):
    http_url(args.link)
    values = args.model_dump(mode="json", exclude_defaults=True)
    values.setdefault("category", args.category.value)
    OpportunitySubmit.model_validate(values)
    note = field_lines(
        {k: v for k, v in values.items() if k != "title"},
        {"link": "Link", "deadline_date": "Deadline"},
    )
    return Proposal(
        f"Suggest {args.title} to the Blesser catalog?",
        values,
        note + "\nBlesser reviews suggestions before they appear for everyone.",
    )


async def apply_submit(session, user_id, arguments):
    from api.core.ratelimit import enforce

    enforce("submit", user_id)
    row = await opportunities.submit(
        session, user_id, OpportunitySubmit.model_validate(arguments)
    )
    return Applied(
        {"opportunity_id": row["id"], "title": row["title"], "status": row["status"]},
        "Sent to Blesser for review."
        if row["status"] != "published"
        else "Added to the catalog.",
    )


TOOLS = [
    Tool(
        "search_catalog",
        CatalogSearch,
        "Search the member opportunity catalog by a few keywords and optional filters. Use a blank query for broad or deadline searches.",
        "Searched the Blesser catalog",
        "read",
        read=search_catalog,
        private=False,
        tags=frozenset({"catalog"}),
    ),
    Tool(
        "get_opportunity",
        OpportunityLookup,
        "Read one published opportunity by a catalog id or slug.",
        "Checked an opportunity",
        "read",
        read=get_opportunity,
        private=False,
        tags=frozenset({"catalog"}),
    ),
    Tool(
        "list_for_you",
        ForYou,
        "Read the open listings that best fit the member's match profile (their For you list), best fit first.",
        "Checked your For you list",
        "read",
        read=list_for_you,
        tags=frozenset({"catalog"}),
    ),
    Tool(
        "search_web",
        WebSearch,
        "Search the public web for opportunity information after checking the catalog. Use public terms only. Results are search snippets.",
        "Searched the web",
        "read",
        read=search_web,
        private=False,
        needs_session=False,
    ),
    Tool(
        "track_opportunity",
        OpportunityLookup,
        "Propose tracking a catalog opportunity, or one of the member's own scan finds, in their applications.",
        "Track opportunity",
        "change",
        propose=propose_track,
        apply=apply_track,
    ),
    Tool(
        "submit_opportunity",
        SubmitOpportunity,
        "Propose suggesting a new opportunity to the Blesser catalog, as the member would from the app. It is reviewed before it appears. Check the catalog first so it is not a duplicate. Use only details the member gave or a source confirmed.",
        "Suggest an opportunity",
        "change",
        propose=propose_submit,
        apply=apply_submit,
    ),
]
