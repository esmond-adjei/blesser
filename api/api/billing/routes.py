"""Your plan: limits, what's included, and this month's use."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.billing import checkout
from api.billing import service as billing
from api.core.db import get_session

router = APIRouter(tags=["billing"])


@router.get("/billing/plan")
async def my_plan(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await billing.summary(session, current.id)


class PlanSwitch(BaseModel):
    plan: str


@router.put("/billing/plan")
async def switch_plan(
    body: PlanSwitch,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Development only (BILLING_PLAN_SWITCH): pick this account's plan."""
    return await billing.switch_plan(session, current.id, body.plan)


class CheckoutStart(BaseModel):
    plan: str


class CheckoutComplete(BaseModel):
    session: str
    card_number: str


@router.post("/billing/checkout")
async def start_checkout(
    body: CheckoutStart,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Switch plan: a free plan applies at once, a paid one returns a checkout session."""
    return await checkout.start(session, current.id, body.plan)


@router.get("/billing/checkout")
async def describe_checkout(
    session_token: str = Query(alias="session"),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return checkout.describe(current.id, session_token)


@router.post("/billing/checkout/complete")
async def complete_checkout(
    body: CheckoutComplete,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await checkout.complete(session, current.id, body.session, body.card_number)
