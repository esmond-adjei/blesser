"""Run routes: runs, lifecycle, progress, deletion, event feed."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import models as auth_models
from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user, get_sse_user
from api.billing import service as billing
from api.core.db import get_session
from api.core.ratelimit import rate_limit
from api.prospects import schemas as prospect_schemas
from api.prospects import service as prospect_service
from api.providers import service as providers_service
from api.runs import interests as run_interests
from api.runs import removal as run_removal
from api.runs import schemas as run_schemas
from api.runs import service as run_service

router = APIRouter(tags=["runs"])


async def _owned_flow(session, user_id: str, flow_id: str | None) -> str | None:
    """A run may only use the caller's own flow ("standard" = built-in)."""
    if not flow_id or flow_id == "standard":
        return None
    from api.flows import service as flows

    return (await flows.get_flow_or_404(session, user_id, flow_id)).id


@router.post(
    "/runs/interest-suggestions", response_model=run_schemas.InterestSuggestionsOut
)
async def interest_suggestions(
    body: run_schemas.InterestSuggestionsIn | None = None,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Proposed run interests drawn from your CVs, each citing its source."""
    await billing.require_feature(session, current.id, "interest_suggestions")
    await billing.check_quota(session, current.id, "model_tokens_per_month")
    return run_schemas.InterestSuggestionsOut(
        **await run_interests.suggest_interests(
            session, current.id, body.document_id if body else None
        )
    )


@router.get("/runs/{run_id}/budget", response_model=run_schemas.RunBudgetOut)
async def get_run_budget(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """How much of the run's research allowance is spent."""
    from api.runs.budgets import run_budget

    run = await run_service.get_run_or_404(session, run_id, current.id)
    return run_schemas.RunBudgetOut(**await run_budget(session, run))


@router.post("/runs", response_model=run_schemas.RunOut, dependencies=[Depends(rate_limit("agent_work"))])
async def create_run(
    req: run_schemas.CreateRunRequest,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Create a run and enqueue its discovery."""
    max_professors = await billing.gate_new_run(session, current.id, req.max_professors)
    run = await run_service.create_run(
        session,
        current.id,
        region=req.region,
        field=req.field,
        degree_level=req.degree_level,
        interest_statement=req.interest_statement,
        interest_document_id=req.interest_document_id,
        max_programs=req.max_programs,
        max_professors=max_professors,
        max_professors_per_program=req.max_professors_per_program,
        flow_id=await _owned_flow(session, current.id, req.flow_id),
        school_tiers=req.school_tiers,
        llm_provider=await providers_service.run_provider(session, current.id, req.llm_provider),
    )
    return run_schemas.RunOut(**await run_service.run_detail(session, run))


@router.post("/runs/from-list", response_model=run_schemas.RunOut, dependencies=[Depends(rate_limit("agent_work"))])
async def create_run_from_list(
    req: prospect_schemas.CreateRunFromListRequest,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Start a run from explicit programs, skipping discovery."""
    max_professors = await billing.gate_new_run(session, current.id, req.max_professors)
    run = await prospect_service.seed_run(
        session,
        current.id,
        degree_level=req.degree_level,
        interest_statement=req.interest_statement,
        interest_document_id=req.interest_document_id,
        programs=req.programs,
        region="(preselected list)",
        field="(preselected list)",
        max_programs=req.max_programs,
        max_professors=max_professors,
        max_professors_per_program=req.max_professors_per_program,
        flow_id=await _owned_flow(session, current.id, req.flow_id),
        llm_provider=await providers_service.run_provider(session, current.id, req.llm_provider),
    )
    return run_schemas.RunOut(**await run_service.run_detail(session, run))


@router.get("/runs", response_model=list[run_schemas.RunListOut])
async def list_runs(
    limit: int | None = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Runs newest first, with live progress counts."""
    return [
        run_schemas.RunListOut(**d)
        for d in await run_service.list_runs(session, current.id, limit, offset)
    ]


@router.get("/runs/estimate", response_model=run_schemas.RunEstimateOut)
async def estimate_run(
    max_programs: int = Query(10, ge=1, le=run_schemas.MAX_PROGRAMS_LIMIT),
    max_professors: int = Query(30, ge=1, le=run_schemas.MAX_PROFESSORS_LIMIT),
    max_professors_per_program: int = Query(5, ge=1, le=run_schemas.MAX_PER_PROGRAM_LIMIT),
    llm_provider: str | None = Query(None, max_length=32),
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Estimated model tokens for a run with these dials, and today's shared allowance left."""
    from api.runs.estimate import estimate_run as project

    return await project(
        session,
        current.id,
        max_programs=max_programs,
        max_professors=max_professors,
        max_professors_per_program=max_professors_per_program,
        llm_provider=await providers_service.run_provider(session, current.id, llm_provider),
    )


@router.get("/runs/{run_id}", response_model=run_schemas.RunOut)
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    run = await run_service.get_run_or_404(session, run_id, current.id)
    return run_schemas.RunOut(**await run_service.run_detail(session, run))


@router.patch("/runs/{run_id}", response_model=run_schemas.RunOut)
async def update_run(
    run_id: str,
    req: run_schemas.RunUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Retune a run mid-flight; changes apply to later saves and spawns."""
    data = req.model_dump(exclude_unset=True)
    if "llm_provider" in data:
        data["llm_provider"] = await providers_service.run_provider(
            session, current.id, data["llm_provider"]
        )
    if "max_professors" in data:
        user = await session.get(auth_models.User, current.id)
        data["max_professors"] = billing.cap_per_run(user, data["max_professors"])
    run = await run_service.update_run(session, current.id, run_id, data)
    return run_schemas.RunOut(**await run_service.run_detail(session, run))


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Halt a run, keeping its history."""
    return await run_service.set_run_status(session, current.id, run_id, "cancelled")


@router.post("/runs/{run_id}/pause")
async def pause_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await run_service.set_run_status(session, current.id, run_id, "paused")


@router.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await run_service.resume_run(session, current.id, run_id)


@router.post("/runs/{run_id}/agents/{task_type}/{action}")
async def control_agent(
    run_id: str,
    task_type: str,
    action: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Pause, resume or cancel one agent (task type) in a run."""
    return await run_service.control_agent(session, current.id, run_id, task_type, action)


@router.post("/runs/{run_id}/retry-failed", dependencies=[Depends(rate_limit("agent_work"))])
async def retry_failed(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Requeue every failed task of a run; they resume from checkpoints."""
    return await run_service.retry_failed(session, current.id, run_id)


@router.get("/runs/{run_id}/refusals", response_model=run_schemas.RefusalsOut)
async def run_refusals(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Why the run's researched professors weren't saved, plus refusals by check code."""
    from api.runs.refusals import run_refusals as summarize

    return await summarize(session, current.id, run_id)


@router.get("/runs/{run_id}/usage", response_model=run_schemas.UsageOut)
async def run_usage(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Cost accounting for a run."""
    data = await run_service.run_usage(session, current.id, run_id)
    return run_schemas.UsageOut(
        **{
            **data,
            "tools": {
                name: run_schemas.ToolStatOut(**stat)
                for name, stat in data["tools"].items()
            },
        },
    )


@router.get("/runs/{run_id}/faculty", response_model=list[run_schemas.RunFacultyOut])
async def run_faculty(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Every professor in a run, with this run's candidate link."""
    return [
        run_schemas.RunFacultyOut(**row)
        for row in await prospect_service.run_faculty(session, current.id, run_id)
    ]


@router.get("/runs/{run_id}/delete-preview")
async def delete_preview(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Per-table row counts deleting this run would remove."""
    return await run_removal.delete_preview(session, current.id, run_id)


@router.delete("/runs/{run_id}")
async def delete_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Delete a run and everything under it, including schools no other run uses."""
    return await run_removal.delete_run(session, current.id, run_id)


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_sse_user),
):
    """Server-sent event feed for a run; the token rides `?token=` (EventSource can't set headers).

    Stays open past `done`: a run's queue can refill."""
    await run_service.get_run_or_404(session, run_id, current.id)
    # The stream outlives the request; don't hold its connection.
    await session.close()
    return StreamingResponse(
        run_service.run_events(run_id, current.id),
        media_type="text/event-stream",
        headers=run_service.SSE_HEADERS,
    )
