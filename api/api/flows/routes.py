"""Agent flow routes: list built-ins + yours, duplicate, edit, delete."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session
from api.core.exceptions import NotFoundError
from api.flows import service as flows
from api.flows.models import AgentFlow

router = APIRouter(tags=["flows"])


class FlowCreate(BaseModel):
    """Duplicate a built-in flow or one of yours."""

    source: str = Field(default="standard", max_length=64)
    name: str = Field(min_length=1, max_length=80)


class FlowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    steps: list[dict] | None = None


@router.get("/flows")
async def list_flows(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Built-in flows (read-only) and your own, plus step descriptions."""
    rows = (
        (
            await session.execute(
                select(AgentFlow)
                .where(AgentFlow.user_id == current.id)
                .order_by(AgentFlow.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "steps": [{"type": t, **flows.STEP_META[t]} for t in flows.STEP_ORDER],
        "flows": [*flows.BUILTINS.values(), *[flows.flow_out(r) for r in rows]],
    }


@router.post("/flows")
async def create_flow(
    req: FlowCreate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    if req.source in flows.BUILTINS:
        base, steps = req.source, flows.BUILTINS[req.source]["steps"]
    else:
        src = await flows.get_flow_or_404(session, current.id, req.source)
        base, steps = src.base, src.steps
    row = AgentFlow(
        user_id=current.id,
        name=req.name.strip(),
        base=base,
        steps=flows.validate_steps([dict(s) for s in steps]),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return flows.flow_out(row)


@router.patch("/flows/{flow_id}")
async def update_flow(
    flow_id: str,
    req: FlowUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    if flow_id in flows.BUILTINS:
        raise NotFoundError("Built-in flows can't be edited; duplicate one instead.")
    row = await flows.get_flow_or_404(session, current.id, flow_id)
    if req.name is not None:
        row.name = req.name.strip()
    if req.steps is not None:
        row.steps = flows.validate_steps(req.steps)
    await session.commit()
    await session.refresh(row)
    return flows.flow_out(row)


@router.delete("/flows/{flow_id}")
async def delete_flow(
    flow_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Runs that used it fall back to Standard."""
    row = await flows.get_flow_or_404(session, current.id, flow_id)
    await session.delete(row)
    await session.commit()
    return {"status": "deleted"}
