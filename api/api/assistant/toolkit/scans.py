from typing import Annotated

from pydantic import Field, StringConstraints

from api.core.exceptions import BadRequestError, RateLimitError
from api.opportunities.models import OpportunityCategory
from api.scans import service as scans
from api.scans import sources

from .base import (
    Applied,
    MemberLookup,
    Proposal,
    RecordId,
    Tool,
    ToolInput,
    bulk,
    field_lines,
    matching,
    preview,
    quoted,
    record,
)

CATEGORY_LABELS = {"startup": "Startups", "research": "Research", "student": "Students"}


def _category_label(value):
    return CATEGORY_LABELS.get(value, str(value).capitalize())


class ScanLookup(ToolInput):
    scan_id: RecordId


class StartScan(ToolInput):
    category: OpportunityCategory
    region: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = (
        ""
    )
    focus: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] = (
        ""
    )
    sites: list[
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
    ] = Field(default_factory=list, max_length=scans.MAX_SCAN_SITES)


class SourceLookup(ToolInput):
    source_id: RecordId


class AddSource(ToolInput):
    url: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)
    ]
    category: OpportunityCategory
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""


class SourceChanges(ToolInput):
    category: OpportunityCategory | None = None
    note: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None
    ) = None
    paused: bool | None = None


class UpdateSource(SourceLookup):
    changes: SourceChanges


SCAN_FIELDS = (
    "id",
    "kind",
    "status",
    "region",
    "categories",
    "focus",
    "sites",
    "opportunities_found",
    "opportunities_added",
    "created_at",
    "finished_at",
)


def _scan_title(scan):
    categories = ", ".join(_category_label(c) for c in scan["categories"])
    return f"{categories} in {scan['region']}" if scan.get("region") else categories


def _scan_record(scan):
    out = record(scan, SCAN_FIELDS)
    out["focus"] = (scan.get("focus") or "")[:300]
    return out


async def allowance(session, user_id, args, registry):
    return await scans.scan_allowance(session, user_id), None


async def list_scans(session, user_id, args, registry):
    rows = await scans.list_scans(session, user_id, limit=50)
    rows = matching(
        rows, args.query, ("region", "focus", "status", "kind", "categories")
    )
    items = []
    for row in rows[:12]:
        key = registry.register(
            "scan",
            {"id": row["id"], "title": _scan_title(row)},
            detail=row["status"].capitalize(),
        )
        items.append({**_scan_record(row), "source": key})
    return {
        "items": items,
        "total": len(rows),
        "scope": "The member's scans, newest first. kind member is a scan they started, sources is a check of My sources. Use get_scan for what a scan found.",
    }, len(rows)


async def get_scan(session, user_id, args, registry):
    scan = await scans.scan_detail(session, user_id, args.scan_id)
    key = registry.register(
        "scan",
        {"id": scan["id"], "title": _scan_title(scan)},
        detail=scan["status"].capitalize(),
    )
    finds = []
    for row in scan.get("finds") or []:
        find_key = registry.register(
            "find",
            {
                "id": row["opportunity_id"],
                "title": row["title"],
                "deadline_date": row.get("deadline_date"),
            },
            detail="Waiting for review" if row["in_review"] else "",
            url=f"/scans/{scan['id']}",
        )
        finds.append(
            {
                "opportunity_id": row["opportunity_id"],
                "title": row["title"],
                "category": row["category"],
                "kind": row["kind"],
                "is_new": row["is_new"],
                "in_review": row["in_review"],
                "source": find_key,
                "deadline": registry.deadlines.get(find_key),
            }
        )
    return {
        **_scan_record(scan),
        "source": key,
        "finds": finds[:30],
        "total_finds": len(finds),
        "scope": "Finds in review are visible to this member only until Blesser reviews them. They can still be tracked with track_opportunity.",
    }, len(finds)


async def propose_start(session, user_id, args):
    left = await scans.scan_allowance(session, user_id)
    if left["enabled"] and (left["left_this_hour"] < 1 or left["left_today"] < 1):
        raise RateLimitError(
            "The member has no scans left for now. Say when more are available instead of proposing one."
        )
    sites = await scans.check_sites(args.sites)
    region = args.region
    values = {
        "category": args.category.value,
        "region": region,
        "focus": args.focus,
        "sites": sites,
    }
    # The category and region are already in the question above.
    note = field_lines(
        {
            **({} if region else {"region": "Your default region"}),
            **({"focus": args.focus} if args.focus else {}),
            **({"sites": sites} if sites else {}),
        }
    )
    if left["enabled"]:
        note += f"{chr(10) if note else ''}Uses 1 of the {left['left_today']} scans you have left today."
    where = f" in {region}" if region else ""
    return Proposal(
        f"Start a scan for {args.category.value} opportunities{where}?",
        values,
        note,
        "Start scan",
    )


async def apply_start(session, user_id, arguments):
    from api.core.ratelimit import check_scan_limit

    await check_scan_limit(session, user_id)
    scan = await scans.start_scan(
        session,
        user_id,
        categories=[arguments["category"]],
        region=arguments["region"],
        focus=arguments["focus"],
        sites=await scans.check_sites(arguments["sites"]),
    )
    title = _scan_title({"categories": scan.categories, "region": scan.region})
    return Applied(
        {
            "scan_id": scan.id,
            "status": scan.status,
            "message": "The scan runs in the background and usually takes a few minutes. Use get_scan later to read its finds.",
        },
        "Started your scan. It runs in the background.",
        preview("scan", scan.id, title, "Running"),
    )


async def propose_cancel(session, user_id, args):
    scan = await scans.scan_detail(session, user_id, args.scan_id)
    if scan["status"] != "running":
        raise BadRequestError("This scan is not running.")
    return Proposal(
        f"Stop the scan for {_scan_title(scan)}?",
        {"scan_id": scan["id"]},
        "Finds saved so far stay in your scan.",
        "Stop scan",
    )


async def apply_cancel(session, user_id, arguments):
    scan = await scans.cancel_scan(session, user_id, arguments["scan_id"])
    return Applied(
        {"scan_id": scan["id"], "status": scan["status"]},
        "Stopped the scan.",
        preview("scan", scan["id"], _scan_title(scan), scan["status"].capitalize()),
    )


async def propose_delete_scan(session, user_id, args):
    scan = await scans.scan_detail(session, user_id, args.scan_id)
    return Proposal(
        f"Delete the scan for {_scan_title(scan)}?",
        {"scan_id": scan["id"]},
        "Opportunities it found stay in the catalog and in your applications.",
        "Delete",
    )


async def apply_delete_scan(session, user_id, arguments):
    await scans.delete_scan(session, user_id, arguments["scan_id"])
    return Applied({"deleted": True}, "Deleted the scan.")


def _source_record(row):
    out = sources.source_out(row)
    return {
        **record(
            out, ("id", "url", "category", "note", "paused", "finds", "last_scan_id")
        ),
        "last_checked": out["last_checked_at"].date().isoformat()
        if out["last_checked_at"]
        else None,
    }


async def list_sources(session, user_id, args, registry):
    rows = [_source_record(row) for row in await sources.list_sources(session, user_id)]
    rows = matching(rows, args.query, ("url", "note", "category"))
    from api.core.config import settings

    return {
        "items": rows,
        "total": len(rows),
        "max_sources": settings.member_sources_max,
        "check_every_days": settings.member_source_check_days,
        "scope": "Sites the member saved so Blesser checks them on a schedule.",
    }, len(rows)


async def _source(session, user_id, source_id):
    return await sources._get(session, user_id, source_id)


async def propose_add_source(session, user_id, args):
    sites = await scans.check_sites([args.url])
    if not sites:
        raise BadRequestError("Give a site address.")
    values = {"url": sites[0], "category": args.category.value, "note": args.note}
    return Proposal(
        f"Add {sites[0]} to your sources?",
        values,
        field_lines(
            {
                "category": _category_label(args.category.value),
                **({"note": args.note} if args.note else {}),
            },
            {"category": "Looking for"},
        ),
        "Add source",
    )


async def apply_add_source(session, user_id, arguments):
    row = await sources.add_source(
        session,
        user_id,
        url=arguments["url"],
        category=arguments["category"],
        note=arguments["note"],
    )
    return Applied(
        {"source_id": row.id, "url": row.url},
        "Added to your sources. Blesser checks it on the next hourly pass.",
        preview("site", row.id, row.url, _category_label(row.category)),
    )


class AddSources(ToolInput):
    items: list[AddSource] = Field(min_length=1, max_length=10)


propose_add_sources, apply_add_sources = bulk(
    propose_add_source, apply_add_source, noun="source", plural="sources"
)


async def propose_update_source(session, user_id, args):
    row = await _source(session, user_id, args.source_id)
    changes = args.changes.model_dump(
        mode="json", exclude_unset=True, exclude_none=True
    )
    if not changes:
        raise BadRequestError("Supply at least one change.")
    shown = dict(changes)
    if "category" in shown:
        shown["category"] = _category_label(shown["category"])
    if "paused" in shown:
        shown["paused"] = "Paused" if shown["paused"] else "Checked on schedule"
    return Proposal(
        f"Update {row.url} in your sources?",
        {"source_id": row.id, "changes": changes},
        field_lines(shown, {"category": "Looking for", "paused": "Checks"}),
    )


async def apply_update_source(session, user_id, arguments):
    row = await sources.update_source(
        session, user_id, arguments["source_id"], arguments["changes"]
    )
    return Applied(
        _source_record(row),
        "Updated the source.",
        preview(
            "site",
            row.id,
            row.url,
            "Paused" if row.paused else _category_label(row.category),
        ),
    )


async def propose_delete_source(session, user_id, args):
    row = await _source(session, user_id, args.source_id)
    return Proposal(
        f"Remove {row.url} from your sources?",
        {"source_id": row.id},
        "Finds from earlier checks stay in your scans.",
        "Delete",
    )


async def apply_delete_source(session, user_id, arguments):
    await sources.delete_source(session, user_id, arguments["source_id"])
    return Applied({"deleted": True}, "Removed the source.")


async def propose_check(session, user_id, args):
    rows = [r for r in await sources.list_sources(session, user_id) if not r.paused]
    if not rows:
        raise BadRequestError("The member has no active sources to check.")
    names = ", ".join(quoted(r.url, 60) for r in rows[:5])
    more = f" and {len(rows) - 5} more" if len(rows) > 5 else ""
    return Proposal(
        "Check your sources now?",
        {},
        f"Sites: {names}{more}\nThis does not use your scan allowance. Checks can run once an hour.",
        "Check now",
    )


async def apply_check(session, user_id, arguments):
    started = await sources.check_now(session, user_id)
    first = started[0]
    return Applied(
        {"scan_ids": [scan.id for scan in started]},
        "Started checking your sources.",
        preview(
            "scan",
            first.id,
            _scan_title({"categories": first.categories, "region": ""}),
            "Checking your sources",
        ),
    )


TOOLS = [
    Tool(
        "scan_allowance",
        ToolInput,
        "Read how many scans the member can still start this hour and today.",
        "Checked your scan allowance",
        "read",
        read=allowance,
    ),
    Tool(
        "list_scans",
        MemberLookup,
        "Read the member's recent scans with status and find counts, optionally filtered by region, focus or status.",
        "Checked your scans",
        "read",
        read=list_scans,
    ),
    Tool(
        "get_scan",
        ScanLookup,
        "Read one of the member's scans and what it found, by scan_id.",
        "Checked a scan",
        "read",
        read=get_scan,
    ),
    Tool(
        "start_scan",
        StartScan,
        "Propose starting a scan that sends an agent to look for new opportunities in one category, with an optional region, focus and up to five public sites to read first. Uses the member's scan allowance.",
        "Start a scan",
        "change",
        propose=propose_start,
        apply=apply_start,
    ),
    Tool(
        "cancel_scan",
        ScanLookup,
        "Propose stopping one of the member's running scans.",
        "Stop a scan",
        "delete",
        propose=propose_cancel,
        apply=apply_cancel,
    ),
    Tool(
        "delete_scan",
        ScanLookup,
        "Propose deleting one of the member's scans from their list. Found opportunities stay.",
        "Delete a scan",
        "delete",
        propose=propose_delete_scan,
        apply=apply_delete_scan,
    ),
    Tool(
        "list_sources",
        MemberLookup,
        "Read the member's My sources list: sites Blesser checks for them on a schedule.",
        "Checked your sources",
        "read",
        read=list_sources,
    ),
    Tool(
        "add_source",
        AddSource,
        "Propose adding a public site to the member's sources, with the category to look for and an optional note on what they want from it.",
        "Add a source",
        "change",
        propose=propose_add_source,
        apply=apply_add_source,
    ),
    Tool(
        "add_sources",
        AddSources,
        "Propose adding several public sites to the member's sources at once, up to ten, each with a category and an optional note. One approval covers them all. Use this instead of add_source when there is more than one site.",
        "Add sources",
        "change",
        propose=propose_add_sources,
        apply=apply_add_sources,
    ),
    Tool(
        "update_source",
        UpdateSource,
        "Propose changing a source's category or note, or pausing or resuming its checks.",
        "Update a source",
        "change",
        propose=propose_update_source,
        apply=apply_update_source,
    ),
    Tool(
        "delete_source",
        SourceLookup,
        "Propose removing a site from the member's sources.",
        "Remove a source",
        "delete",
        propose=propose_delete_source,
        apply=apply_delete_source,
    ),
    Tool(
        "check_sources",
        ToolInput,
        "Propose checking all of the member's active sources now. Allowed once an hour and does not use the scan allowance.",
        "Check your sources",
        "change",
        propose=propose_check,
        apply=apply_check,
    ),
]
