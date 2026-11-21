import logging
import time
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB

from api.agent.orchestrator import TaskHalted, _halt_reason
from api.agent.tools.context import ToolContext
from api.core.config import settings
from api.core.ids import new_id
from api.core.time import utcnow_naive
from api.editorial.service import get_settings
from api.opportunities import service
from api.opportunities.crawl_models import CrawlCandidate, Source
from api.opportunities.crawler import crawl_due, record_candidate
from api.opportunities.dedupe import key_for
from api.opportunities.extraction import extract_page
from api.opportunities.official import (
    aggregator_hosts,
    host_of,
    is_aggregator,
    resolve_official,
)
from api.opportunities.page_cache import get_page
from api.opportunities.tools import _scan_created, handle_save_opportunity, record_fetch
from api.opportunities.triage import (
    is_listing,
    names_other_country,
    triage_page,
    triage_url,
)


def add_reason(metrics: dict, reason: str) -> None:
    reasons = metrics.setdefault("triaged_out", {})
    reasons[reason] = reasons.get(reason, 0) + 1


async def lock_claim(session, candidate, token) -> bool:
    await session.refresh(candidate, with_for_update=True)
    if candidate.claim_token == token:
        return True
    await session.commit()
    return False


def claim_order():
    """Newest items first, then sources that have yielded saves, then newest found.

    Yield is smoothed ((saved + 1) / (found + 2)) so a new source starts at one half.
    """
    source_yield = (func.coalesce(Source.opportunities_saved, 0) + 1.0) / (
        func.coalesce(Source.candidates_found, 0) + 2.0
    )
    return (
        CrawlCandidate.published_date.desc().nulls_last(),
        source_yield.desc(),
        CrawlCandidate.created_at.desc(),
    )


log = logging.getLogger(__name__)


async def claim_candidate(session, category: str, region: str):
    now = utcnow_naive()
    query = (
        select(CrawlCandidate)
        .where(
            or_(
                CrawlCandidate.status == "new",
                (CrawlCandidate.status == "rejected")
                & CrawlCandidate.reason.startswith("scope:")
                & ~CrawlCandidate.reason.startswith(
                    f"scope:{region.strip().casefold()}:{category}:", autoescape=True
                ),
            ),
            CrawlCandidate.reason != "region_excluded:" + region.strip().casefold(),
            or_(
                CrawlCandidate.claimed_until.is_(None),
                CrawlCandidate.claimed_until < now,
            ),
            or_(
                cast(CrawlCandidate.category_hints, JSONB) == [],
                cast(CrawlCandidate.category_hints, JSONB).contains([category]),
            ),
        )
        .outerjoin(Source, Source.id == CrawlCandidate.source_id)
        .order_by(*claim_order())
        .with_for_update(skip_locked=True, of=CrawlCandidate)
        .limit(1)
    )
    row = (await session.execute(query)).scalar_one_or_none()
    if row:
        row.claim_token = new_id()
        row.claimed_until = now + timedelta(minutes=15)
    await session.commit()
    return row


async def follow_aggregator(ctx, page, data, hosts, metrics: dict):
    """Swap an aggregator post for the official page it links to, when one checks out.

    Returns the data to save and the extra save arguments: where it was found, and a
    hold for review when no official page was found."""
    resolution = await resolve_official(
        page,
        title=data.title,
        organization=data.organization,
        deadline=data.deadline,
        preferred_link=data.link,
        hosts=hosts,
        fetch=get_page,
    )
    if resolution.page is None:
        metrics["official_missing"] = metrics.get("official_missing", 0) + 1
        return data, {
            "found_via": page.url,
            "review_reason": "no_official_link",
            "review_note": (
                f"Found on {host_of(page.url)}, an aggregator, and no official page "
                "could be confirmed from it. Add the official link before publishing."
            ),
        }
    metrics["official_found"] = metrics.get("official_found", 0) + 1
    official = resolution.url
    record_fetch(ctx, official, resolution.page.text)
    link = data.link
    if not link or is_aggregator(link, hosts) or host_of(link) != host_of(official):
        link = official
    changes = {"source_url": official, "link": link}
    if resolution.deadline_changed:
        changes["deadline"] = resolution.deadline or ""
    if resolution.deadline_unclear:
        # The official page does not settle the date: an editor decides.
        ctx.extraction_confidence = 0
    return data.model_copy(update=changes), {"found_via": page.url}


async def run_pipeline(session, task, scan, category: str, on_event=None) -> dict:
    started = time.monotonic()
    metrics = dict(task.metrics or {})
    crawl = await crawl_due(session, categories=[category])
    metrics["candidates_found"] = (
        metrics.get("candidates_found", 0) + crawl["candidates_found"]
    )
    metrics["sources"] = {**metrics.get("sources", {}), **crawl["sources"]}
    ctx = ToolContext(session, scan)
    ctx.category = category
    # Crawler saves have their own budget: they never use up the agent's room.
    ctx.save_via = "crawler"
    ctx.opportunities_saved = metrics.get("crawler_saved", 0)
    limit = (await get_settings(session))["crawler"]["max_candidates_per_task"]
    hosts = await aggregator_hosts(session)
    attempts = 0
    for _ in range(limit * 10):
        if (
            attempts >= limit
            or ctx.opportunities_saved >= settings.max_opportunities_per_task
        ):
            break
        if (
            await _scan_created(session, scan.id, via="crawler")
            >= settings.max_opportunities_per_run
        ):
            break
        if halted := await _halt_reason(ctx):
            raise TaskHalted(halted)
        candidate = await claim_candidate(session, category, scan.region)
        if candidate is None:
            break
        token = candidate.claim_token
        metrics["candidates_considered"] = metrics.get("candidates_considered", 0) + 1
        reason = await triage_url(session, candidate)
        if reason is None and names_other_country(
            f"{candidate.url} {candidate.title}", scan.region
        ):
            reason = "region_excluded:" + scan.region.strip().casefold()
        page = None
        if reason is None:
            await session.commit()
            page = (
                await get_page(candidate.url, need="outbound")
                if is_aggregator(candidate.url, hosts)
                else await get_page(candidate.url)
            )
            metrics["cache_hits"] = metrics.get("cache_hits", 0) + int(page.cached)
            if not await lock_claim(session, candidate, token):
                continue
            reason = await triage_page(session, candidate, page, service.today())
            candidate.content_hash = page.content_hash
            if reason is None and is_listing(page):
                for item in page.metadata["links"]:
                    if item["url"] != candidate.url:
                        added = await record_candidate(
                            session,
                            **item,
                            source_id=candidate.source_id,
                            category_hints=candidate.category_hints,
                        )
                        metrics["candidates_found"] += int(added)
                        if added and candidate.source_id:
                            await session.execute(
                                update(Source)
                                .where(Source.id == candidate.source_id)
                                .values(candidates_found=Source.candidates_found + 1)
                            )
                reason = "listing_expanded"
        if reason is not None:
            if page is None and not await lock_claim(session, candidate, token):
                continue
            candidate.status = (
                "new"
                if reason.startswith(("fetch_failed:", "region_excluded:"))
                else "closed"
                if reason == "deadline_passed"
                else "duplicate"
                if "duplicate" in reason
                else "rejected"
            )
            candidate.reason = reason
            add_reason(
                metrics,
                reason.partition(":")[0]
                if reason.startswith("region_excluded:")
                else reason,
            )
        else:
            attempts += 1
            metrics["extraction_attempts"] = metrics.get("extraction_attempts", 0) + 1
            task.metrics = dict(metrics)
            await session.commit()
            try:
                result = await extract_page(
                    page,
                    category=category,
                    region=scan.region,
                    today=service.today().isoformat(),
                )
                metrics["extracted"] = metrics.get("extracted", 0) + 1
                if not await lock_claim(session, candidate, token):
                    continue
                if halted := await _halt_reason(ctx):
                    raise TaskHalted(halted)
                if not result.relevant or result.opportunity is None:
                    candidate.status, candidate.reason = (
                        "rejected",
                        result.reason or "not_relevant",
                    )
                    add_reason(metrics, "not_relevant")
                elif not result.region_eligible:
                    candidate.status, candidate.reason = (
                        "new",
                        "region_excluded:" + scan.region.strip().casefold(),
                    )
                    add_reason(metrics, "region_excluded")
                else:
                    data = result.opportunity
                    candidate.dedupe_key = await key_for(
                        session, data.organization, data.title
                    )
                    if data.category.value not in scan.categories:
                        candidate.status, candidate.reason = "new", "category_deferred"
                        candidate.category_hints = [data.category.value]
                        add_reason(metrics, "category_deferred")
                    elif await service.blocks_save(session, candidate.dedupe_key):
                        candidate.status, candidate.reason = "duplicate", "dedupe_key"
                        add_reason(metrics, "dedupe_key")
                    elif data.source_url != page.url:
                        candidate.status, candidate.reason = (
                            "rejected",
                            "source_mismatch",
                        )
                        add_reason(metrics, "source_mismatch")
                    else:
                        record_fetch(ctx, page.url, page.text)
                        ctx.extraction_confidence = result.confidence
                        follow = {}
                        if is_aggregator(page.url, hosts):
                            data, follow = await follow_aggregator(
                                ctx, page, data, hosts, metrics
                            )
                            if not await lock_claim(session, candidate, token):
                                continue
                        saved = await handle_save_opportunity(
                            data.model_dump(mode="json"), ctx, commit=False, **follow
                        )
                        if "error" in saved:
                            candidate.status, candidate.reason = (
                                "rejected",
                                saved["error"],
                            )
                            add_reason(metrics, "grounding")
                        else:
                            candidate.status, candidate.reason = (
                                "extracted",
                                result.reason,
                            )
                            candidate.opportunity_id = saved["opportunity_id"]
                            metrics["saved"] = metrics.get("saved", 0) + int(
                                saved["created"]
                            )
                            metrics["crawler_saved"] = metrics.get(
                                "crawler_saved", 0
                            ) + int(saved["created"])
                            if candidate.source_id and saved["created"]:
                                await session.execute(
                                    update(Source)
                                    .where(Source.id == candidate.source_id)
                                    .values(
                                        opportunities_saved=Source.opportunities_saved
                                        + 1
                                    )
                                )
            except (ValueError, ValidationError) as exc:
                if not await lock_claim(session, candidate, token):
                    continue
                candidate.status, candidate.reason = (
                    "rejected",
                    "invalid_extraction: " + str(exc)[:200],
                )
                add_reason(metrics, "invalid_extraction")
        candidate.claim_token = None
        candidate.claimed_until = (
            utcnow_naive() + timedelta(minutes=30)
            if candidate.reason.startswith("fetch_failed:")
            else None
        )
        metrics["pipeline_seconds"] = round(time.monotonic() - started, 2)
        task.metrics = dict(metrics)
        await session.commit()
        if on_event:
            await on_event(
                {
                    "turn": 0,
                    "tool": "crawl_candidate",
                    "input": {"url": candidate.url},
                    "result": {"status": candidate.status, "reason": candidate.reason},
                    "ok": candidate.status == "extracted",
                }
            )
    metrics["pipeline_seconds"] = round(time.monotonic() - started, 2)
    task.metrics = metrics
    await session.commit()
    log.info(
        "crawler: scan %s %s in %s: %s checked, %s read, %s saved, skipped %s (%ss)",
        scan.id[:8],
        category,
        scan.region,
        metrics.get("candidates_considered", 0),
        metrics.get("extracted", 0),
        metrics.get("crawler_saved", 0),
        metrics.get("triaged_out", {}),
        metrics["pipeline_seconds"],
    )
    return metrics
