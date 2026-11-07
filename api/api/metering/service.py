"""Account-level metering, recorded at the call site.

Rollups only: each billable call upserts one row per (account, UTC day,
feature, provider, model), pruned after USAGE_RETENTION_DAYS. Metering never
breaks the call it measures. "scoring", "search" and "verification" are
counted on admission (api/billing `reserve_tool_call`), not after the call.
"""

import logging
import math
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from api.core.config import settings
from api.core.db import SessionLocal
from api.metering.models import UsageDaily

log = logging.getLogger(__name__)

_last_prune: date | None = None


def _today() -> date:
    return datetime.now(UTC).date()


#: Per-day row of tokens reserved by in-flight model calls (api/billing);
#: counted by spend gates, hidden from usage displays.
RESERVED_FEATURE = "_reserved"


def usage_upsert(
    user_id: str,
    feature: str,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    calls: int = 1,
    day: date | None = None,
):
    stmt = insert(UsageDaily).values(
        user_id=user_id,
        day=day or _today(),
        feature=feature[:32],
        provider=(provider or "unknown")[:32],
        model=(model or "unknown")[:128],
        calls=calls,
        input_tokens=int(input_tokens or 0),
        output_tokens=int(output_tokens or 0),
    )
    return stmt.on_conflict_do_update(
        index_elements=["user_id", "day", "feature", "provider", "model"],
        set_={
            "calls": UsageDaily.calls + stmt.excluded.calls,
            "input_tokens": UsageDaily.input_tokens + stmt.excluded.input_tokens,
            "output_tokens": UsageDaily.output_tokens + stmt.excluded.output_tokens,
        },
    )


async def record(
    user_id: str | None,
    feature: str,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    calls: int = 1,
) -> None:
    if not user_id:
        return
    try:
        async with SessionLocal() as session:
            await session.execute(
                usage_upsert(
                    user_id,
                    feature,
                    provider,
                    model,
                    input_tokens,
                    output_tokens,
                    calls,
                )
            )
            await session.commit()
        await _maybe_prune()
    except Exception as exc:  # noqa: BLE001 - metering never breaks the metered call
        log.warning("usage metering failed (%s/%s): %s", feature, provider, exc)


async def _maybe_prune() -> None:
    global _last_prune
    today = _today()
    if _last_prune == today:
        return
    _last_prune = today
    await prune()


async def prune(retention_days: int | None = None) -> int:
    cutoff = _today() - timedelta(days=retention_days or settings.usage_retention_days)
    async with SessionLocal() as session:
        result = await session.execute(
            delete(UsageDaily).where(UsageDaily.day < cutoff)
        )
        await session.commit()
        return result.rowcount or 0


def billable_input_tokens(usage: dict) -> int:
    """Prompt tokens weighted by cost: cache reads at a tenth, cache writes at
    1.25x, so quotas count cached prompts at their price."""
    total = int(usage.get("input_tokens", 0) or 0)
    read = int(usage.get("cache_read_tokens", 0) or 0)
    write = int(usage.get("cache_write_tokens", 0) or 0)
    return max(total - read + math.ceil(read / 10) + math.ceil(write / 4), 0)


class MeteredProvider:
    """Wraps an LLM provider; records usage from each response."""

    def __init__(self, inner, user_id: str | None, feature: str):
        self._inner = inner
        self._user_id = user_id
        self._feature = feature

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def _record(self, response) -> None:
        usage = getattr(response, "usage", None) or {}
        await record(
            self._user_id,
            self._feature,
            getattr(self._inner, "name", "") or type(self._inner).__name__,
            getattr(self._inner, "model", "") or "",
            billable_input_tokens(usage),
            usage.get("output_tokens", 0),
        )

    async def chat(self, *args, **kwargs):
        response = await self._inner.chat(*args, **kwargs)
        await self._record(response)
        return response

    async def chat_stream(self, *args, **kwargs):
        async for event in self._inner.chat_stream(*args, **kwargs):
            if event.get("type") == "done":
                await self._record(event.get("response"))
            yield event


def metered(provider, user_id: str | None, feature: str):
    return MeteredProvider(provider, user_id, feature)


async def summary(session, user_id: str | None, days: int) -> dict:
    """Per-day and per-feature totals; user_id None = every account (ops)."""
    since = _today() - timedelta(days=days - 1)
    base = [UsageDaily.day >= since, UsageDaily.feature != RESERVED_FEATURE]
    if user_id is not None:
        base.append(UsageDaily.user_id == user_id)
    sums = (
        func.sum(UsageDaily.calls),
        func.sum(UsageDaily.input_tokens),
        func.sum(UsageDaily.output_tokens),
    )

    def rows(*keys):
        return select(*keys, *sums).where(*base).group_by(*keys).order_by(*keys)

    by_day = (await session.execute(rows(UsageDaily.day))).all()
    by_feature = (
        await session.execute(
            rows(UsageDaily.feature, UsageDaily.provider, UsageDaily.model)
        )
    ).all()
    by_day_feature = (await session.execute(rows(UsageDaily.day, UsageDaily.feature))).all()
    prev_since = since - timedelta(days=days)
    prev_base = [UsageDaily.day >= prev_since, UsageDaily.day < since, *base[1:]]
    prev = (await session.execute(select(*sums).where(*prev_base))).one()
    day_map = {d: (c, i, o) for d, c, i, o in by_day}
    out = {
        "since": since.isoformat(),
        "days": [
            {
                "day": (since + timedelta(days=n)).isoformat(),
                "calls": int(day_map.get(since + timedelta(days=n), (0, 0, 0))[0] or 0),
                "input_tokens": int(
                    day_map.get(since + timedelta(days=n), (0, 0, 0))[1] or 0
                ),
                "output_tokens": int(
                    day_map.get(since + timedelta(days=n), (0, 0, 0))[2] or 0
                ),
            }
            for n in range(days)
        ],
        "by_feature": [
            {
                "feature": f,
                "provider": p,
                "model": m,
                "calls": int(c or 0),
                "input_tokens": int(i or 0),
                "output_tokens": int(o or 0),
            }
            for f, p, m, c, i, o in by_feature
        ],
        # Tokens per day split by feature, for a stacked chart.
        "by_day_feature": [
            {"day": d.isoformat(), "feature": f, "calls": int(c or 0), "tokens": int(i or 0) + int(o or 0)}
            for d, f, c, i, o in by_day_feature
        ],
        # The same length of time just before, to compare against.
        "previous": {
            "calls": int(prev[0] or 0),
            "input_tokens": int(prev[1] or 0),
            "output_tokens": int(prev[2] or 0),
        },
    }
    out["totals"] = {
        k: sum(d[k] for d in out["days"])
        for k in ("calls", "input_tokens", "output_tokens")
    }
    return out


async def top_accounts(session, days: int, limit: int = 20) -> list[dict]:
    """Ops: heaviest accounts in the window (abuse monitoring)."""
    from api.auth.models import User

    since = _today() - timedelta(days=days - 1)
    tokens = func.sum(UsageDaily.input_tokens + UsageDaily.output_tokens)
    q = (
        select(User.email, func.sum(UsageDaily.calls), tokens)
        .join(User, User.id == UsageDaily.user_id)
        .where(UsageDaily.day >= since, UsageDaily.feature != RESERVED_FEATURE)
        .group_by(User.email)
        .order_by(tokens.desc())
        .limit(limit)
    )
    return [
        {"email": e, "calls": int(c or 0), "tokens": int(t or 0)}
        for e, c, t in (await session.execute(q)).all()
    ]
