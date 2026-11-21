"""Move existing listings off aggregator pages.

Listings saved before official.py existed (or before a site was added to the aggregator
list) can still point members at an aggregator post. For each one this follows the post
to the official page, the same way new finds are followed:

- Official page found: `source_url` and `link` point at it, and the post moves to
  `found_via_url`. When the official page shows a different deadline, a single clear
  date replaces the old one; an unclear one sends a published listing to review.
- No official page: a published listing goes to review with
  `review_reason = no_official_link`; other listings only record where they came from.

Each listing is tried at most once every `RECHECK_DAYS` (`official_checked_at`).

Run a dry run first, which reads pages but changes nothing:

    uv run python -m api.opportunities.official_backfill            # dry run
    uv run python -m api.opportunities.official_backfill --apply

The worker also runs a small applied pass every hour once `official_backfill` is
switched on in admin settings.
"""

import argparse
import asyncio
import json
import re
from datetime import timedelta

from sqlalchemy import or_, select

from api.applications.dates import parse_deadline
from api.core.time import utcnow_naive
from api.opportunities.models import Opportunity, OpportunityStatus
from api.opportunities.official import (
    aggregator_hosts,
    host_of,
    is_aggregator,
    resolve_official,
)
from api.opportunities.page_content import normalized_url

#: A listing whose official page was not found is tried again after this long.
RECHECK_DAYS = 30
#: Listings handled per scheduled pass.
PASS_SIZE = 10

PUBLISHED = OpportunityStatus.published.value
REVIEW = OpportunityStatus.in_review.value


def _host_pattern(hosts) -> str:
    """Matches normalized URLs (`https://host/...`) on any of the hosts or their subdomains."""
    names = "|".join(re.escape(h) for h in sorted(hosts))
    return rf"^https://([^/]*\.)?({names})(/|$)"


def due_query(hosts, now, limit: int, *, recheck: bool = True):
    pattern = _host_pattern(hosts)
    query = select(Opportunity).where(
        or_(
            Opportunity.source_url_key.op("~")(pattern),
            Opportunity.link_key.op("~")(pattern),
        ),
        Opportunity.status != OpportunityStatus.hidden.value,
        or_(
            Opportunity.review_reason.is_(None),
            Opportunity.review_reason != "no_official_link",
        ),
    )
    if recheck:
        query = query.where(
            or_(
                Opportunity.official_checked_at.is_(None),
                Opportunity.official_checked_at < now - timedelta(days=RECHECK_DAYS),
            )
        )
    return query.order_by(
        (Opportunity.status == PUBLISHED).desc(), Opportunity.created_at
    ).limit(limit)


def _append_note(opp: Opportunity, note: str) -> None:
    if note not in (opp.editor_note or ""):
        opp.editor_note = ((opp.editor_note or "").rstrip() + "\n\n" + note).strip()


async def check_listing(opp: Opportunity, hosts, *, fetch=None) -> dict:
    """Find the official page for one listing, without changing it."""
    if fetch is None:
        from api.opportunities.page_cache import get_page as fetch
    post = opp.source_url if is_aggregator(opp.source_url, hosts) else opp.link
    own_link = "" if is_aggregator(opp.link, hosts) else opp.link
    page = await fetch(post, need="outbound")
    report = {
        "id": opp.id,
        "title": opp.title,
        "status": opp.status,
        "aggregator_url": post,
    }
    if page.error:
        return {**report, "outcome": "unresolved", "why": page.error}
    resolution = await resolve_official(
        page,
        title=opp.title,
        organization=opp.organization,
        deadline=opp.deadline_date.isoformat() if opp.deadline_date else "",
        preferred_link=own_link,
        hosts=hosts,
        fetch=fetch,
    )
    if resolution.page is None:
        return {
            **report,
            "outcome": "unresolved",
            "why": "no linked page names it",
            "tried": resolution.tried,
        }
    official = resolution.url
    link = own_link if own_link and host_of(own_link) == host_of(official) else official
    return {
        **report,
        "outcome": "deadline_unclear" if resolution.deadline_unclear else "resolved",
        "official_url": official,
        "link": link,
        "deadline": resolution.deadline if resolution.deadline_changed else None,
    }


def apply_result(opp: Opportunity, result: dict, now) -> None:
    post = result["aggregator_url"]
    if not opp.found_via_url:
        opp.found_via_url = normalized_url(post)
    opp.official_checked_at = now
    if result["outcome"] == "unresolved":
        if opp.status == PUBLISHED:
            opp.status, opp.review_reason = REVIEW, "no_official_link"
        _append_note(
            opp,
            f"Listed from {host_of(post)}, an aggregator, and no official page could "
            "be confirmed from it. Add the official link before publishing.",
        )
        return
    opp.source_url, opp.link = result["official_url"], result["link"]
    opp.source_hash = ""
    if result["outcome"] == "deadline_unclear":
        if opp.status == PUBLISHED:
            opp.status, opp.review_reason = REVIEW, "source_changed"
        _append_note(
            opp,
            "The official page does not show this listing's deadline. Check the date "
            "before publishing.",
        )
        return
    if result["deadline"] is not None:
        opp.deadline = result["deadline"]
        opp.deadline_date = parse_deadline(result["deadline"])
    opp.verified_at = now


async def run_backfill(
    session, *, apply: bool, limit: int = PASS_SIZE, fetch=None
) -> dict:
    """One pass over listings on aggregator pages. A dry run changes nothing."""
    hosts = await aggregator_hosts(session)
    counts = {"checked": 0, "resolved": 0, "deadline_unclear": 0, "unresolved": 0}
    report = {"apply": apply, "counts": counts, "listings": []}
    if not hosts:
        return report
    now = utcnow_naive()
    rows = (
        (await session.execute(due_query(hosts, now, limit, recheck=apply)))
        .scalars()
        .all()
    )
    if apply:
        # Claim first so a parallel pass (or a crash mid-way) does not retry at once.
        for opp in rows:
            opp.official_checked_at = now
        await session.commit()
    for opp in rows:
        result = await check_listing(opp, hosts, fetch=fetch)
        counts["checked"] += 1
        counts[result["outcome"]] += 1
        report["listings"].append(result)
        if apply:
            fresh = await session.get(
                Opportunity, opp.id, with_for_update=True, populate_existing=True
            )
            if fresh is not None and fresh.status != OpportunityStatus.hidden.value:
                apply_result(fresh, result, utcnow_naive())
            await session.commit()
    return report


async def scheduled_pass(session) -> dict | None:
    """The worker's hourly pass, when staff have switched it on."""
    from api.editorial.service import get_settings

    if not (await get_settings(session)).get("official_backfill"):
        return None
    report = await run_backfill(session, apply=True)
    return report["counts"] if report["counts"]["checked"] else None


async def _main(apply: bool, limit: int) -> None:
    from api.core.db import SessionLocal

    async with SessionLocal() as session:
        report = await run_backfill(session, apply=apply, limit=limit)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="change the listings")
    parser.add_argument("--limit", type=int, default=500, help="listings to check")
    args = parser.parse_args()
    asyncio.run(_main(args.apply, args.limit))
