"""Entitlements and the one enforcement primitive.

Every gate goes through `require_feature` or `check_quota`, which raise
UpgradeRequiredError (402) for the webapp's UpgradePrompt. No ad-hoc plan checks.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select, text, update

from api.auth import models as auth_models
from api.billing.plans import FEATURES, PLANS, QUOTA_NOUN, QUOTAS, UPGRADE_TO, Plan
from api.core.config import settings
from api.core.db import SessionLocal
from api.core.exceptions import (
    BadRequestError,
    ForbiddenError,
    NotFoundError,
    UpgradeRequiredError,
)

log = logging.getLogger(__name__)


def _month_start():
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).replace(
        tzinfo=None
    )


def plans_apply() -> bool:
    """Whether accounts get their stored plan; otherwise everyone is Beta."""
    return settings.billing_enforced or settings.billing_plan_switch


def plan_for(user: auth_models.User) -> Plan:
    if not plans_apply():
        return PLANS["beta"]
    return PLANS.get(user.plan or "free", PLANS["free"])


def system_daily_cap(plan: Plan | None) -> int:
    """Daily tokens this plan gets on the system model; 0 is no cap."""
    if plan is None or plan.system_tokens_per_day is None:
        return max(settings.system_model_daily_tokens, 0)
    return plan.system_tokens_per_day


def daily_ceilings(user: auth_models.User | None) -> tuple[int, int]:
    """(model tokens, operator tool calls) allowed per day on the operator's keys;
    0 = no ceiling. Plans without daily ceilings (Beta) are exempt."""
    # A missing account row falls back to the ceilings rather than none.
    plan = plan_for(user) if user is not None else None
    exempt = (user is not None or not plans_apply()) and (
        plan is None or not plan.daily_ceilings
    )
    if exempt:
        return 0, 0
    return system_daily_cap(plan), settings.system_daily_tool_calls


async def usage_this_month(session, user_id: str) -> dict[str, int]:
    from api.metering.models import UsageDaily
    from api.runs.models import Run

    start = _month_start()
    runs = (
        await session.execute(
            select(func.count())
            .select_from(Run)
            .where(Run.user_id == user_id, Run.created_at >= start)
        )
    ).scalar() or 0
    tokens = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(UsageDaily.input_tokens + UsageDaily.output_tokens), 0
                )
            ).where(UsageDaily.user_id == user_id, UsageDaily.day >= start.date())
        )
    ).scalar() or 0
    return {"runs_per_month": int(runs), "model_tokens_per_month": int(tokens)}


def _upgrade(
    kind: str, key: str, plan: Plan, message: str, **extra
) -> UpgradeRequiredError:
    return UpgradeRequiredError(
        message,
        {
            "code": "upgrade_required",
            "kind": kind,
            "key": key,
            "label": FEATURES.get(key) or QUOTAS.get(key) or key,
            "plan": plan.id,
            "upgrade_to": UPGRADE_TO,
            **extra,
        },
    )


async def require_feature(session, user_id: str, feature: str) -> None:
    user = await session.get(auth_models.User, user_id)
    plan = plan_for(user)
    if feature not in plan.features:
        raise _upgrade(
            "feature",
            feature,
            plan,
            f"{FEATURES[feature]} is part of {PLANS[UPGRADE_TO].label}.",
        )


async def check_quota(session, user_id: str, quota: str, adding: int = 1) -> None:
    """Refuse when this action would take the account past its quota."""
    user = await session.get(auth_models.User, user_id)
    plan = plan_for(user)
    limit = plan.quotas.get(quota)
    if limit is None:
        return
    used = (await usage_this_month(session, user_id)).get(quota, 0)
    # Count quotas refuse the exceeding action; the token allowance refuses new
    # work once spent (calls can't be sized before they run).
    over = used >= limit if quota == "model_tokens_per_month" else used + adding > limit
    if over:
        raise _upgrade(
            "quota",
            quota,
            plan,
            f"{plan.label} includes {limit:,} {QUOTA_NOUN[quota]} a month and you've used "
            f"{used:,}. {PLANS[UPGRADE_TO].label} raises the limit, or wait for the reset on the 1st.",
            noun=QUOTA_NOUN[quota],
            used=used,
            limit=limit,
        )


def uses_operator_key(llm_kwargs: dict) -> bool:
    """True when these factory kwargs spend the operator's env key."""
    key = settings.llm_api_key
    if not key:
        return False  # nothing to protect (keyless local model)
    return llm_kwargs.get("api_key", key) == key


async def tokens_today(session, user_id: str) -> int:
    from api.metering.models import UsageDaily

    today = datetime.now(UTC).date()
    return int(
        (
            await session.execute(
                select(
                    func.coalesce(
                        func.sum(UsageDaily.input_tokens + UsageDaily.output_tokens), 0
                    )
                ).where(UsageDaily.user_id == user_id, UsageDaily.day == today)
            )
        ).scalar()
        or 0
    )


async def check_model_allowance(session, user_id: str | None, llm_kwargs: dict) -> None:
    """Plan's monthly token quota, plus operator-key rules (allowed, verified email,
    daily ceiling incl. in-flight reservations) when the call spends that key.
    Spenders go through `reserve_model_call`, which runs this under the account lock."""
    if user_id is None:
        return
    await check_quota(session, user_id, "model_tokens_per_month")
    if not uses_operator_key(llm_kwargs):
        return
    if not settings.allow_system_model:
        raise ForbiddenError(
            "This server has no shared model. Add your own model and key in "
            "Settings > Models."
        )
    user = await session.get(auth_models.User, user_id)
    if settings.system_model_requires_verified_email and (
        user is None or user.email_verified_at is None
    ):
        raise ForbiddenError(
            "Confirm your email address to use the shared model, or add your "
            "own model key in Settings > Models."
        )
    cap, _ = daily_ceilings(user)
    if cap > 0 and await tokens_today(session, user_id) >= cap:
        raise ForbiddenError(
            f"You've used today's {cap:,}-token allowance on the shared model. "
            "Add your own key in Settings > Models, or continue tomorrow."
        )


# Reserve-or-refuse: check and bookkeeping share one transaction under a
# per-account advisory lock, else concurrent calls all read the same total and
# pass. Model calls reserve an estimate (a RESERVED_FEATURE row, released once
# real usage is recorded); tool calls count on admission. A reservation a
# crashed process never releases lapses at the UTC day boundary.


@dataclass(frozen=True)
class Reservation:
    user_id: str
    day: date
    tokens: int


async def _lock_account(session, user_id: str) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"spend:{user_id}"},
    )


def estimate_tokens(messages, system: str | None, max_tokens: int) -> int:
    """Rough upper estimate: the whole output budget plus ~4 characters per input token."""
    image_tokens = 0
    counted = []
    for message in messages:
        item = dict(message)
        if item.get("attachments"):
            attachments = []
            for attachment in item["attachments"]:
                if attachment.get("kind") == "image":
                    image_tokens += 4096
                    attachments.append({"kind": "image", "name": attachment.get("name", "")})
                else:
                    attachments.append(attachment)
            item["attachments"] = attachments
        counted.append(item)
    size = len(json.dumps(counted, default=str)) + len(system or "")
    return int(max_tokens) + image_tokens + size // 4


async def reserve_model_call(
    user_id: str | None, llm_kwargs: dict, estimate: int
) -> Reservation | None:
    """Run the allowance rules and reserve `estimate` tokens atomically; pair every
    reservation with `release`."""
    if user_id is None:
        return None
    from api.metering.service import RESERVED_FEATURE, usage_upsert

    tokens = max(int(estimate), 1)
    day = datetime.now(UTC).date()
    async with SessionLocal() as session:
        await _lock_account(session, user_id)
        await check_model_allowance(session, user_id, llm_kwargs)
        await session.execute(
            usage_upsert(
                user_id,
                RESERVED_FEATURE,
                "-",
                "-",
                input_tokens=tokens,
                calls=0,
                day=day,
            )
        )
        await session.commit()
    return Reservation(user_id, day, tokens)


async def release(reservation: Reservation | None) -> None:
    """Drop a reservation; the call's real usage is metered separately."""
    if reservation is None:
        return
    from api.metering.models import UsageDaily
    from api.metering.service import RESERVED_FEATURE

    try:
        async with SessionLocal() as session:
            await session.execute(
                update(UsageDaily)
                .where(
                    UsageDaily.user_id == reservation.user_id,
                    UsageDaily.day == reservation.day,
                    UsageDaily.feature == RESERVED_FEATURE,
                )
                .values(
                    input_tokens=func.greatest(
                        UsageDaily.input_tokens - reservation.tokens, 0
                    )
                )
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001 - never mask the call's own outcome
        log.warning("releasing a token reservation failed: %s", exc)


#: Usage features spending operator-held keys outside the model; they share one
#: per-account daily call allowance.
OPERATOR_TOOL_FEATURES = ("search", "scoring", "verification")


async def tool_calls_today(session, user_id: str) -> int:
    from api.metering.models import UsageDaily

    today = datetime.now(UTC).date()
    return int(
        (
            await session.execute(
                select(func.coalesce(func.sum(UsageDaily.calls), 0)).where(
                    UsageDaily.user_id == user_id,
                    UsageDaily.day == today,
                    UsageDaily.feature.in_(OPERATOR_TOOL_FEATURES),
                )
            )
        ).scalar()
        or 0
    )


async def reserve_tool_call(
    user_id: str | None, feature: str, provider: str, model: str = ""
) -> None:
    """Meter one operator-paid tool call, or raise ForbiddenError past today's
    SYSTEM_DAILY_TOOL_CALLS. Counted on admission, so a failing call still counts."""
    if user_id is None:
        return
    from api.metering.service import usage_upsert

    async with SessionLocal() as session:
        await _lock_account(session, user_id)
        _, cap = daily_ceilings(await session.get(auth_models.User, user_id))
        if cap > 0 and await tool_calls_today(session, user_id) >= cap:
            raise ForbiddenError(
                f"You've used today's {cap:,} search, scoring and verification "
                "calls. Continue tomorrow."
            )
        await session.execute(usage_upsert(user_id, feature, provider, model))
        await session.commit()


async def tool_call_refusal(
    user_id: str | None, feature: str, provider: str, model: str = ""
) -> str | None:
    """`reserve_tool_call` for tool handlers: the refusal as text."""
    try:
        await reserve_tool_call(user_id, feature, provider, model)
    except ForbiddenError as exc:
        return exc.message
    return None


async def gate_new_run(session, user_id: str, max_professors: int | None) -> int:
    """Run-creation gate: monthly run quota, then the per-run professor cap.
    Returns the professor budget to store."""
    await check_quota(session, user_id, "runs_per_month")
    user = await session.get(auth_models.User, user_id)
    requested = (
        max_professors
        if max_professors is not None
        else settings.max_candidates_per_run
    )
    return cap_per_run(user, requested)


def cap_per_run(user: auth_models.User, requested: int | None) -> int | None:
    """Clamp a run's professor budget to the plan's per-run quota."""
    limit = plan_for(user).quotas.get("professors_per_run")
    if limit is None or requested is None:
        return requested
    return min(requested, limit)


def _catalog_entry(plan: Plan) -> dict:
    return {
        "id": plan.id,
        "label": plan.label,
        "monthly_price_usd": plan.monthly_price_usd,
        "features": [v for k, v in FEATURES.items() if k in plan.features],
        "quotas": [
            {"key": k, "label": v, "limit": plan.quotas.get(k)}
            for k, v in QUOTAS.items()
        ],
    }


async def summary(session, user_id: str) -> dict:
    user = await session.get(auth_models.User, user_id)
    plan = plan_for(user)
    used = await usage_this_month(session, user_id)
    return {
        "plan": {"id": plan.id, "label": plan.label},
        "enforced": plans_apply(),
        "switchable": settings.billing_plan_switch,
        "plans": [{"id": p.id, "label": p.label} for p in PLANS.values()]
        if settings.billing_plan_switch
        else [],
        "catalog": [_catalog_entry(p) for p in PLANS.values() if p.purchasable],
        "features": [
            {"key": k, "label": v, "included": k in plan.features}
            for k, v in FEATURES.items()
        ],
        "quotas": [
            {"key": k, "label": v, "limit": plan.quotas.get(k), "used": used.get(k)}
            for k, v in QUOTAS.items()
        ],
        # The system model's daily allowance (Auto): null limit = unlimited.
        "system_model": {
            "daily_limit": daily_ceilings(user)[0] or None,
            "used_today": await tokens_today(session, user_id),
        },
    }


async def switch_plan(session, user_id: str, plan_id: str) -> dict:
    """Store the account's plan and return its summary; 404 unless BILLING_PLAN_SWITCH."""
    if not settings.billing_plan_switch:
        raise NotFoundError("Plan switching is not available on this server.")
    if plan_id not in PLANS:
        raise BadRequestError(
            f"Unknown plan {plan_id!r}. Choose one of: {', '.join(PLANS)}.",
            field="plan",
            value=plan_id,
        )
    from api.billing import checkout

    user = await session.get(auth_models.User, user_id)
    await checkout.apply_plan(session, user, plan_id)
    return await summary(session, user_id)
