import asyncio

import pytest
from sqlalchemy import func, select

from api.agent.tools import ToolContext, dispatch
from api.candidates.models import CandidateScore
from api.core.db import SessionLocal
from api.prospects.models import Professor, Program, RunSchool, School
from api.runs.lifecycle import note_tasks_drained
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID

NARROW = "research_one_professor"


async def _setup(programmes: int, **budgets) -> tuple[str, list[str]]:
    async with SessionLocal() as session:
        run = Run(
            user_id=TEST_USER_ID,
            region="U",
            field="f",
            degree_level="phd",
            interest_statement="robots",
            status="running",
            **budgets,
        )
        session.add(run)
        await session.flush()
        ids = []
        for i in range(programmes):
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run.id)], name=f"Uni {i}")
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name=f"P{i}")
            session.add(program)
            await session.flush()
            ids.append(program.id)
            session.add(
                ResearchTask(
                    run_id=run.id,
                    user_id=TEST_USER_ID,
                    task_type="research_professor",
                    target_id=program.id,
                    target_name=program.name,
                )
            )
        await session.commit()
        return run.id, ids


async def _supervisor_spawns(run_id: str, program_id: str, names: list[str]) -> dict:
    async with SessionLocal() as session:
        run = await session.get(Run, run_id)
        program = await session.get(Program, program_id)
        sup = (
            await session.execute(
                select(ResearchTask).where(
                    ResearchTask.run_id == run_id,
                    ResearchTask.task_type == "research_professor",
                    ResearchTask.target_id == program_id,
                )
            )
        ).scalar_one()
        sup.status = TaskStatus.running
        await session.commit()
        ctx = ToolContext(session=session, run=run, program=program)
        out = await dispatch("spawn_professor_research", {"names": names}, ctx)
        sup.status = TaskStatus.done
        await session.commit()
        await note_tasks_drained(session, run_id)
        await session.commit()
        return out


async def _open_and_saved(session, run_id: str) -> tuple[int, int]:
    open_count = (
        await session.execute(
            select(func.count())
            .select_from(ResearchTask)
            .where(
                ResearchTask.run_id == run_id,
                ResearchTask.task_type == NARROW,
                ResearchTask.status.in_([TaskStatus.pending, TaskStatus.running]),
            )
        )
    ).scalar()
    saved = (
        await session.execute(
            select(func.count())
            .select_from(CandidateScore)
            .where(CandidateScore.run_id == run_id)
        )
    ).scalar()
    return int(open_count or 0), int(saved or 0)


async def _work_narrow_tasks(run_id: str, cap: int, matches) -> None:
    """Play the worker: run pending narrow tasks oldest first, saving a candidate when `matches(name)`."""
    while True:
        async with SessionLocal() as session:
            task = (
                await session.execute(
                    select(ResearchTask)
                    .where(
                        ResearchTask.run_id == run_id,
                        ResearchTask.task_type == NARROW,
                        ResearchTask.status == TaskStatus.pending,
                    )
                    .order_by(ResearchTask.created_at)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if task is None:
                return
            open_count, saved = await _open_and_saved(session, run_id)
            assert saved + open_count <= cap
            task.status = TaskStatus.running
            await session.commit()
            if matches(task.target_name) and saved < cap:
                professor = Professor(
                    user_id=TEST_USER_ID, program_id=task.target_id, name=task.target_name
                )
                session.add(professor)
                await session.flush()
                session.add(
                    CandidateScore(
                        run_id=run_id,
                        user_id=TEST_USER_ID,
                        professor_id=professor.id,
                        similarity_score=0.8,
                        rationale="r",
                    )
                )
            task.status = TaskStatus.done
            await session.commit()
            await note_tasks_drained(session, run_id)
            await session.commit()


async def _researched_by_programme(run_id: str) -> dict[str, int]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(ResearchTask.target_id, ResearchTask.status).where(
                    ResearchTask.run_id == run_id, ResearchTask.task_type == NARROW
                )
            )
        ).all()
    out: dict[str, int] = {}
    for target, status in rows:
        out.setdefault(target, 0)
        if status == TaskStatus.done:
            out[target] += 1
    return out


def _names(i: int, n: int = 5) -> list[str]:
    return [f"Prof {i}-{k}" for k in range(n)]


def _half(name: str) -> bool:
    return int(name.rsplit("-", 1)[1]) % 2 == 0


@pytest.mark.parametrize("programmes", [10, 20])
def test_every_programme_is_researched(programmes):
    async def scenario():
        run_id, ids = await _setup(
            programmes, max_professors=30, max_professors_per_program=5
        )
        # All supervisors answer before any narrow task runs (stage priority).
        for i, pid in enumerate(ids):
            await _supervisor_spawns(run_id, pid, _names(i))
        await _work_narrow_tasks(run_id, 30, _half)
        async with SessionLocal() as session:
            _, saved = await _open_and_saved(session, run_id)
            run = await session.get(Run, run_id)
            status = run.status
        return await _researched_by_programme(run_id), saved, status

    researched, saved, status = asyncio.run(scenario())
    assert len(researched) == programmes
    assert all(n >= 1 for n in researched.values()), researched
    # 3 of 5 names match per programme: 30 saved for 10, the cap for 20.
    assert saved == 30
    assert status == "done"


def test_small_cap_still_spreads_across_programmes():
    async def scenario():
        run_id, ids = await _setup(10, max_professors=10, max_professors_per_program=5)
        for i, pid in enumerate(ids):
            await _supervisor_spawns(run_id, pid, _names(i))
        await _work_narrow_tasks(run_id, 10, lambda _name: False)
        return await _researched_by_programme(run_id)

    researched = asyncio.run(scenario())
    # No one matches: each programme is researched to its dial, within 2.5 x the cap.
    assert all(n >= 1 for n in researched.values()), researched
    assert sum(researched.values()) == 25


def test_failed_task_frees_its_slot_for_a_waiting_lead():
    async def scenario():
        run_id, ids = await _setup(1, max_professors=30, max_professors_per_program=2)
        out = await _supervisor_spawns(run_id, ids[0], ["Ada", "Grace", "Edsger"])
        async with SessionLocal() as session:
            first = (
                await session.execute(
                    select(ResearchTask)
                    .where(ResearchTask.run_id == run_id, ResearchTask.task_type == NARROW)
                    .order_by(ResearchTask.created_at)
                    .limit(1)
                )
            ).scalar_one()
            first.status = TaskStatus.error
            await session.commit()
            await note_tasks_drained(session, run_id)
            await session.commit()
            rows = (
                await session.execute(
                    select(ResearchTask.target_name, ResearchTask.status)
                    .where(ResearchTask.run_id == run_id, ResearchTask.task_type == NARROW)
                    .order_by(ResearchTask.created_at)
                )
            ).all()
        return out, rows

    out, rows = asyncio.run(scenario())
    assert out["researching_now"] == 2 and out["waiting"] == 1
    assert [tuple(r) for r in rows] == [
        ("Ada", TaskStatus.error),
        ("Grace", TaskStatus.pending),
        ("Edsger", TaskStatus.pending),
    ]


def test_run_concludes_with_only_waiting_leads_left():
    async def scenario():
        run_id, ids = await _setup(1, max_professors=2, max_professors_per_program=5)
        await _supervisor_spawns(run_id, ids[0], _names(0))
        await _work_narrow_tasks(run_id, 2, lambda _name: True)
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            waiting = (
                await session.execute(
                    select(func.count())
                    .select_from(ResearchTask)
                    .where(
                        ResearchTask.run_id == run_id,
                        ResearchTask.status == TaskStatus.deferred,
                    )
                )
            ).scalar()
            return run.status, waiting

    status, waiting = asyncio.run(scenario())
    assert status == "done"
    assert waiting == 3


def test_refusal_summary_counts_leads_never_reached():
    from api.runs.refusals import run_refusals

    async def scenario():
        run_id, ids = await _setup(1, max_professors=2, max_professors_per_program=5)
        await _supervisor_spawns(run_id, ids[0], _names(0))
        await _work_narrow_tasks(run_id, 2, lambda _name: True)
        async with SessionLocal() as session:
            return await run_refusals(session, TEST_USER_ID, run_id)

    summary = asyncio.run(scenario())
    # The cap of 2 filled from the first two names; three were never reached.
    by_gate = {r["gate"]: r["count"] for r in summary["not_saved"]}
    assert summary["researched"] == 2
    assert by_gate["narrow.not_reached"] == 3


def test_raising_the_cap_reopens_a_finished_run():
    from api.runs.service import update_run

    async def scenario():
        run_id, ids = await _setup(1, max_professors=2, max_professors_per_program=5)
        await _supervisor_spawns(run_id, ids[0], _names(0))
        await _work_narrow_tasks(run_id, 2, lambda _name: True)
        async with SessionLocal() as session:
            before = (await session.get(Run, run_id)).status
            run = await update_run(session, TEST_USER_ID, run_id, {"max_professors": 4})
            return before, run.status, await _open_and_saved(session, run_id)

    before, after, (open_count, saved) = asyncio.run(scenario())
    assert before == "done"
    assert after == "running"
    assert (open_count, saved) == (2, 2)
