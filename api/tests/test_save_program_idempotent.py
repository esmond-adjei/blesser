import asyncio

from sqlalchemy import func, select

from api.agent.tools import ToolContext, dispatch
from api.core.db import SessionLocal
from api.prospects.models import Program, RunSchool
from api.runs.models import ResearchTask, Run
from tests.test_budgets import _make_run

SAVE = {"school_name": "Idempotent University", "program_name": "PhD in Robotics"}


def _counts(run_id):
    async def go():
        async with SessionLocal() as session:
            schools = (
                await session.execute(
                    select(func.count())
                    .select_from(RunSchool)
                    .where(RunSchool.run_id == run_id)
                )
            ).scalar()
            programs = (
                await session.execute(
                    select(func.count())
                    .select_from(Program)
                    .join(RunSchool, Program.school_id == RunSchool.school_id)
                    .where(RunSchool.run_id == run_id)
                )
            ).scalar()
            tasks = (
                await session.execute(
                    select(func.count())
                    .select_from(ResearchTask)
                    .where(
                        ResearchTask.run_id == run_id,
                        ResearchTask.task_type == "research_professor",
                    )
                )
            ).scalar()
            return schools, programs, tasks

    return asyncio.run(go())


async def _save(run_id, payload):
    async with SessionLocal() as session:
        run = await session.get(Run, run_id)
        return await dispatch(
            "save_program", dict(payload), ToolContext(session=session, run=run)
        )


def test_same_save_twice_is_one_row_set():
    run_id = _make_run()
    first = asyncio.run(_save(run_id, SAVE))
    again = asyncio.run(
        _save(
            run_id,
            {
                "school_name": "idempotent  university",
                "program_name": "PhD in robotics.",
            },
        )
    )
    assert again["deduped"] is True
    assert again["program_id"] == first["program_id"]
    assert _counts(run_id) == (1, 1, 1)


def test_concurrent_saves_are_serialized():
    run_id = _make_run()

    async def both():
        return await asyncio.gather(_save(run_id, SAVE), _save(run_id, SAVE))

    a, b = asyncio.run(both())
    assert a["program_id"] == b["program_id"]
    assert _counts(run_id) == (1, 1, 1)


def test_new_programme_at_saved_school_reuses_the_school():
    run_id = _make_run()
    asyncio.run(_save(run_id, SAVE))
    other = asyncio.run(_save(run_id, {**SAVE, "program_name": "MSc in Robotics"}))
    assert "program_id" in other and not other.get("deduped")
    assert _counts(run_id) == (1, 2, 2)
