import argparse
import asyncio
import json
import time
from pathlib import Path

from sqlalchemy import select

import api.models  # noqa: F401
from api.auth.models import User
from api.core.config import settings
from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.opportunities.crawl_models import Source
from api.opportunities.crawler import crawl_due
from api.scans import queue, service
from api.scans.models import ScanTask, WorkerHeartbeat


async def main(args):
    started = time.monotonic()
    report = {"provider": settings.llm_provider, "model": settings.llm_model}
    async with SessionLocal() as session:
        if args.crawl_only:
            report["crawl"] = await crawl_due(session)
        else:
            user_id = (
                await session.execute(
                    select(User.id)
                    .where(User.disabled_at.is_(None))
                    .order_by(User.created_at)
                    .limit(1)
                )
            ).scalar_one()
            scan = await service.start_scan(
                session,
                user_id,
                categories=args.categories,
                focus="Find open opportunities eligible for people in Ghana. Prefer official sources and skip known URLs.",
                commit=False,
            )
            session.add(
                WorkerHeartbeat(
                    worker_id=queue.WORKER_ID,
                    concurrency=3,
                    last_seen_at=utcnow_naive(),
                )
            )
            task_ids = []
            for _ in args.categories:
                claimed = await queue.claim_next_task(
                    session, scan_id=scan.id, commit=False
                )
                task_ids.append(claimed.id)
            await session.commit()
            scan_id = scan.id
            report["scan_id"] = scan_id
            print(json.dumps({"scan_id": scan_id}), flush=True)
    if not args.crawl_only:
        stop = asyncio.Event()

        async def pulse():
            while not stop.is_set():
                async with SessionLocal() as session:
                    await queue.heartbeat(session, concurrency=len(args.categories))
                try:
                    await asyncio.wait_for(stop.wait(), 10)
                except TimeoutError:
                    pass

        async def work(task_id):
            async with SessionLocal() as session:
                task = await session.get(ScanTask, task_id)
                if task is None:
                    return
                token = queue.current_lease.set((task.id, task.attempt))
                try:
                    await queue.process_claimed(session, task)
                finally:
                    queue.current_lease.reset(token)
                    await queue._release_lease(task.id, task.attempt)

        heartbeat = asyncio.create_task(pulse())
        try:
            await asyncio.gather(*(work(id) for id in task_ids))
        finally:
            stop.set()
            await heartbeat
        async with SessionLocal() as session:
            report["scan"] = await service.scan_detail(session, user_id, scan_id)
    async with SessionLocal() as session:
        sources = (await session.execute(select(Source))).scalars().all()
        report["sources"] = [
            {
                "url": s.url,
                "candidates_found": s.candidates_found,
                "saved": s.opportunities_saved,
                "last_error": s.last_error,
            }
            for s in sources
        ]
    report["wall_seconds"] = round(time.monotonic() - started, 2)
    Path(args.output).write_text(json.dumps(report, indent=2, default=str))
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in {"scan", "sources"}
            },
            default=str,
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--crawl-only", action="store_true")
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=["startup", "research", "student"],
        default=["startup", "research", "student"],
    )
    parser.add_argument("--output", required=True)
    asyncio.run(main(parser.parse_args()))
