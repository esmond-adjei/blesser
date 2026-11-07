"""Run-level budget caps; task counters live in api/agent/tools/budgets.py."""

from api.core.config import settings


def run_limit(run, field: str, default: int) -> int:
    """Stored value, else the default."""
    value = getattr(run, field, None)
    return default if value is None else value


def default_run_budgets(
    max_programs: int | None,
    max_professors: int | None,
    max_professors_per_program: int | None,
) -> tuple[int, int, int]:
    """Fill unset budgets with the defaults run_limit would fall back to."""
    return (
        settings.max_programs_per_run if max_programs is None else max_programs,
        settings.max_candidates_per_run if max_professors is None else max_professors,
        settings.max_professors_per_program
        if max_professors_per_program is None
        else max_professors_per_program,
    )


async def run_budget(session, run) -> dict:
    """Used vs limit per cap; agent caps count only the research agent's saves."""
    from sqlalchemy import func, select

    from api.candidates import models as candidate_models
    from api.prospects import models as prospect_models

    async def schools(origin: str) -> int:
        # A school shared between runs counts once per run.
        return (
            await session.execute(
                select(func.count())
                .select_from(prospect_models.RunSchool)
                .where(
                    prospect_models.RunSchool.run_id == run.id,
                    prospect_models.RunSchool.origin == origin,
                )
            )
        ).scalar() or 0

    professors = (
        await session.execute(
            select(func.count())
            .select_from(candidate_models.CandidateScore)
            .where(candidate_models.CandidateScore.run_id == run.id)
        )
    ).scalar() or 0
    return {
        "programs": {
            "used": await schools("agent"),
            "limit": run_limit(run, "max_programs", settings.max_programs_per_run),
        },
        "professors": {
            "used": professors,
            "limit": run_limit(run, "max_professors", settings.max_candidates_per_run),
        },
        "user_programs": {
            "used": await schools("user"),
            "limit": settings.max_user_programs_per_run,
        },
    }
