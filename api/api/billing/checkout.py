"""Plan checkout through the billing provider.

Only the development-only `simulated` provider exists (BILLING_PLAN_SWITCH=true):
it mirrors a Stripe Checkout flow with a local page and test cards. The session
is a short-lived signed token, so no table is needed.

Test cards: 4242 4242 4242 4242 succeeds, 4000 0000 0000 0002 is declined.
"""

from datetime import timedelta

from api.auth import models as auth_models
from api.auth import security
from api.billing.plans import PLANS, Plan
from api.core.config import settings
from api.core.exceptions import BadRequestError
from api.core.time import utcnow_naive

CHECKOUT_TOKEN = "checkout"
CHECKOUT_TTL = timedelta(minutes=30)
TEST_CARD_OK = "4242424242424242"
TEST_CARD_DECLINED = "4000000000000002"


def _purchasable(plan_id: str) -> Plan:
    plan = PLANS.get(plan_id)
    if plan is None or not plan.purchasable:
        offered = ", ".join(p.id for p in PLANS.values() if p.purchasable)
        raise BadRequestError(
            f"Unknown plan {plan_id!r}. Choose one of: {offered}.",
            field="plan",
            value=plan_id,
        )
    return plan


def _provider() -> str:
    provider = (settings.billing_provider or "").lower().strip()
    if provider != "simulated":
        raise BadRequestError(
            f"Billing provider {provider!r} isn't available yet; "
            "set BILLING_PROVIDER=simulated."
        )
    # Simulated checkout marks plans paid with test cards: dev switch only.
    if not settings.billing_plan_switch:
        raise BadRequestError(
            "Simulated checkout is development-only; "
            "set BILLING_PLAN_SWITCH=true to enable it."
        )
    return provider


async def apply_plan(session, user: auth_models.User | None, plan_id: str) -> None:
    """Store the account's plan and mark the choice made."""
    if user is None:
        raise BadRequestError("This account no longer exists.")
    user.plan = plan_id
    user.plan_selected_at = utcnow_naive()
    await session.commit()


async def start(session, user_id: str, plan_id: str) -> dict:
    """Begin switching to `plan_id`: a free plan applies at once, a paid one returns
    the checkout page."""
    plan = _purchasable(plan_id)
    user = await session.get(auth_models.User, user_id)
    if plan.monthly_price_usd <= 0:
        # Free needs no payment, so it applies with or without a provider.
        await apply_plan(session, user, plan.id)
        return {"status": "applied", "plan": plan.id}
    _provider()
    token = security.signed_token(
        CHECKOUT_TOKEN, {"sub": user_id, "plan": plan.id}, CHECKOUT_TTL
    )
    return {"status": "checkout", "plan": plan.id, "session": token}


def _read(user_id: str, token: str) -> Plan:
    claims = security.read_signed(CHECKOUT_TOKEN, token)
    if claims is None or claims.get("sub") != user_id:
        raise BadRequestError(
            "This checkout has expired or belongs to another account. "
            "Pick your plan again.",
            field="session",
        )
    return _purchasable(str(claims.get("plan")))


def describe(user_id: str, token: str) -> dict:
    """What the checkout page shows: the plan and its price."""
    plan = _read(user_id, token)
    return {
        "provider": _provider(),
        "plan": {"id": plan.id, "label": plan.label},
        "monthly_price_usd": plan.monthly_price_usd,
        "test_cards": {"succeeds": TEST_CARD_OK, "declined": TEST_CARD_DECLINED},
    }


async def complete(session, user_id: str, token: str, card_number: str) -> dict:
    """Pay with a test card and apply the plan. A decline is a 400, not a 402 (which
    opens the upgrade prompt)."""
    plan = _read(user_id, token)
    _provider()
    card = "".join(ch for ch in card_number if ch.isdigit())
    if card == TEST_CARD_DECLINED:
        raise BadRequestError(
            "Your card was declined. Try another card.", field="card_number"
        )
    if card != TEST_CARD_OK:
        raise BadRequestError(
            f"Use a test card: {TEST_CARD_OK} succeeds, "
            f"{TEST_CARD_DECLINED} is declined. No real payment is taken.",
            field="card_number",
        )
    user = await session.get(auth_models.User, user_id)
    await apply_plan(session, user, plan.id)
    return {"status": "paid", "plan": plan.id}
