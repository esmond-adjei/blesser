import asyncio
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from api.account import export
from api.applications.models import Application
from api.auth import models as auth_models
from api.candidates import scoring
from api.candidates.models import CandidateScore
from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.main import app
from api.prospects import openalex, optouts, professor_index
from api.prospects import tasks as prospect_tasks
from api.prospects.models import ProfessorIndex, Program, RunSchool, School
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID
from tests.test_pipeline import SaveModel

pytestmark = [pytest.mark.pipeline, pytest.mark.professor_index]

#: The interest each run states, and how a professor scores against it.
UNRELATED, ALIGNED = "medieval poetry", "robot learning"


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _run_at(user_id: str, school_name: str, interest: str, school_id: str | None = None):
    """A run with one programme at the school and its admissions indexed."""

    async def go():
        async with SessionLocal() as session:
            run = Run(
                user_id=user_id, region="U", field="robotics", degree_level="phd",
                interest_statement=interest, status="running", max_professors=100,
            )  # fmt: skip
            session.add(run)
            await session.flush()
            if school_id is None:
                school = School(user_id=user_id, run_links=[RunSchool(run_id=run.id)], name=school_name)
                session.add(school)
                await session.flush()
            else:
                school = await session.get(School, school_id)
                session.add(RunSchool(run_id=run.id, school_id=school.id))
            program = Program(user_id=user_id, school_id=school.id, name=f"Robotics {_uid()}")
            session.add(program)
            session.add(Application(user_id=user_id, run_id=run.id, school=school_name))
            await session.commit()
            return run.id, school.id, program.id

    return asyncio.run(go())


def _research(run_id: str, program_id: str, name: str):
    """Run one narrow task for `name`; returns (result, trace events)."""
    events: list[dict] = []

    async def on_event(event):
        events.append(event)

    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            task = ResearchTask(
                run_id=run_id, user_id=run.user_id, task_type="research_one_professor",
                target_id=program_id, target_name=name, status=TaskStatus.running,
            )  # fmt: skip
            session.add(task)
            await session.commit()
            out = await prospect_tasks.run_research_one_professor(session, task, run, on_event=on_event)
            return out

    return asyncio.run(go()), events


class OpenAlexCalls:
    """Fake OpenAlex that counts calls; one author per name at the school."""

    def __init__(self, monkeypatch, school_name: str):
        self.searches: list[str] = []
        self.works: list[str] = []
        self.school_name = school_name
        monkeypatch.setattr(openalex, "find_author", self.find_author)
        monkeypatch.setattr(openalex, "get_recent_works", self.get_recent_works)
        monkeypatch.setattr(scoring, "score_interest_for_ctx_async", self.score)

    @staticmethod
    def author_id(name: str) -> str:
        return "https://openalex.org/A" + str(abs(hash(name)) % 10**8)

    async def find_author(self, name, hint=None, **_):
        self.searches.append(name)
        return [{"openalex_id": self.author_id(name), "display_name": name, "institution": self.school_name}]

    async def get_recent_works(self, author_id, limit=15, years=None):
        self.works.append(author_id)
        return [
            {"title": f"Learning robot skills, part {k} ({author_id[-4:]})", "abstract": f"Abstract {k}.", "year": 2024, "url": None}
            for k in range(3)
        ]  # fmt: skip

    async def score(self, ctx, interest, texts):
        s = 0.62 if interest == ALIGNED else 0.05
        return {"score": s, "best_index": 0, "all_scores": [s, s / 2, s / 3], "method": "embedding"}


def _entries(user_id: str, name: str) -> list[ProfessorIndex]:
    async def go():
        async with SessionLocal() as session:
            rows = await session.execute(
                select(ProfessorIndex).where(
                    ProfessorIndex.user_id == user_id,
                    ProfessorIndex.name_key == professor_index.name_key(name),
                )
            )
            return list(rows.scalars().all())

    return asyncio.run(go())


def _model(monkeypatch) -> SaveModel:
    import api.agent.orchestrator as orch

    model = SaveModel()
    monkeypatch.setattr(orch, "get_provider", lambda **_: model)
    return model


def test_a_no_match_is_indexed_with_what_the_run_fetched(monkeypatch):
    school = f"Index University {_uid()}"
    name = f"Prof Ada {_uid()}"
    fake = OpenAlexCalls(monkeypatch, school)
    run_id, school_id, program_id = _run_at(TEST_USER_ID, school, UNRELATED)

    out, _ = _research(run_id, program_id, name)

    assert out["final_text"].startswith(f"Researched {name}, not a match")
    assert len(fake.searches) == 1 and len(fake.works) == 1
    [entry] = _entries(TEST_USER_ID, name)
    assert entry.outcome == "no_match" and entry.score == pytest.approx(0.05)
    assert entry.openalex_id == fake.author_id(name).rsplit("/", 1)[-1]
    assert entry.author["display_name"] == name
    assert entry.works[0]["title"].startswith("Learning robot skills, part 0")
    assert (entry.run_id, entry.school_id, entry.school_name) == (run_id, school_id, school)
    assert entry.program_id == program_id and entry.program_name.startswith("Robotics")


def test_a_later_run_scores_from_the_index_without_going_online(monkeypatch):
    school = f"Index University {_uid()}"
    name = f"Prof Babbage {_uid()}"
    fake = OpenAlexCalls(monkeypatch, school)
    first_run, school_id, first_program = _run_at(TEST_USER_ID, school, UNRELATED)
    _research(first_run, first_program, name)
    [before] = _entries(TEST_USER_ID, name)

    model = _model(monkeypatch)
    later_run, _, later_program = _run_at(TEST_USER_ID, school, ALIGNED, school_id=school_id)
    _, events = _research(later_run, later_program, f"Dr. {name}")

    assert len(fake.searches) == 1 and len(fake.works) == 1
    assert [e["tool"] for e in events][:2] == ["professor_index", "score_alignment"]
    assert len(model.calls) == 1

    async def saved():
        async with SessionLocal() as session:
            return (
                await session.execute(
                    select(func.count()).select_from(CandidateScore).where(CandidateScore.run_id == later_run)
                )
            ).scalar()

    assert asyncio.run(saved()) == 1
    [after] = _entries(TEST_USER_ID, name)
    assert after.looked_up_at == before.looked_up_at and after.run_id == first_run


def test_an_author_found_again_reuses_their_indexed_works(monkeypatch):
    school = f"Index University {_uid()}"
    fake = OpenAlexCalls(monkeypatch, school)
    run_id, school_id, program_id = _run_at(TEST_USER_ID, school, UNRELATED)
    name = f"Prof Hopper {_uid()}"
    _research(run_id, program_id, name)
    # A spelling the index lacks: OpenAlex finds the same author and the works come from the index.
    fake.author_id = lambda _n: OpenAlexCalls.author_id(name)  # type: ignore[method-assign]
    later_run, _, later_program = _run_at(TEST_USER_ID, school, UNRELATED, school_id=school_id)
    _, events = _research(later_run, later_program, f"Grace {name}")

    assert len(fake.searches) == 2 and len(fake.works) == 1
    assert "professor_index" in [e["tool"] for e in events]


def test_a_stale_entry_is_looked_up_again_and_refreshed(monkeypatch):
    school = f"Index University {_uid()}"
    name = f"Prof Turing {_uid()}"
    fake = OpenAlexCalls(monkeypatch, school)
    run_id, school_id, program_id = _run_at(TEST_USER_ID, school, UNRELATED)
    _research(run_id, program_id, name)
    old = utcnow_naive() - timedelta(days=31)

    async def age():
        async with SessionLocal() as session:
            entry = (
                await session.execute(
                    select(ProfessorIndex).where(ProfessorIndex.name_key == professor_index.name_key(name))
                )
            ).scalar_one()
            entry.looked_up_at = old
            await session.commit()

    asyncio.run(age())
    later_run, _, later_program = _run_at(TEST_USER_ID, school, UNRELATED, school_id=school_id)
    _research(later_run, later_program, name)

    assert len(fake.searches) == 2 and len(fake.works) == 2
    [entry] = _entries(TEST_USER_ID, name)
    assert entry.looked_up_at > old + timedelta(days=30) and entry.run_id == later_run


def test_another_account_never_sees_the_index(monkeypatch):
    other = f"other-{_uid()}"

    async def make_user():
        async with SessionLocal() as session:
            session.add(auth_models.User(id=other, email=f"{other}@example.com", password_hash="x"))
            await session.commit()

    asyncio.run(make_user())
    school = f"Shared Name University {_uid()}"
    name = f"Prof Lovelace {_uid()}"
    fake = OpenAlexCalls(monkeypatch, school)
    run_id, _, program_id = _run_at(TEST_USER_ID, school, UNRELATED)
    _research(run_id, program_id, name)

    other_run, _, other_program = _run_at(other, school, UNRELATED)
    _research(other_run, other_program, name)

    assert len(fake.searches) == 2 and len(fake.works) == 2
    assert len(_entries(TEST_USER_ID, name)) == 1 and len(_entries(other, name)) == 1

    async def delete_other():
        async with SessionLocal() as session:
            await session.delete(await session.get(auth_models.User, other))
            await session.commit()

    asyncio.run(delete_other())
    assert _entries(other, name) == [] and len(_entries(TEST_USER_ID, name)) == 1


def test_index_is_exported_and_removed_with_an_opt_out(monkeypatch):
    assert "professor_index" in {t.name for t in export.owned_tables()}
    school = f"Index University {_uid()}"
    name = f"Prof Noether {_uid()}"
    OpenAlexCalls(monkeypatch, school)
    run_id, _, program_id = _run_at(TEST_USER_ID, school, UNRELATED)
    _research(run_id, program_id, name)
    assert len(_entries(TEST_USER_ID, name)) == 1

    async def remove():
        async with SessionLocal() as session:
            return await optouts.remove_person(session, name=name, school=school, note="test")

    assert asyncio.run(remove())["indexed"] == 1
    assert _entries(TEST_USER_ID, name) == []


def test_index_off_keeps_nothing(monkeypatch):
    from api.core.config import settings

    monkeypatch.setattr(settings, "professor_index_days", 0)
    school = f"Index University {_uid()}"
    name = f"Prof Curie {_uid()}"
    OpenAlexCalls(monkeypatch, school)
    run_id, _, program_id = _run_at(TEST_USER_ID, school, UNRELATED)
    _research(run_id, program_id, name)
    assert _entries(TEST_USER_ID, name) == []


def test_account_schools_filter_by_tier():
    from api.agent.tools import ToolContext, dispatch
    from api.prospects import tiers

    async def setup():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID, region="U", field="robotics", degree_level="phd",
                interest_statement="robots", status="running", max_programs=10,
                school_tiers=tiers.dump(["strong", "solid"]),
            )  # fmt: skip
            session.add(run)
            # A school a person added earlier, with no tier yet.
            added = School(user_id=TEST_USER_ID, name=f"Added {_uid()}", origin="user")
            session.add(added)
            await session.commit()
            ctx = ToolContext(session=session, run=run)
            strong = f"Strong {_uid()}"
            await dispatch("save_program", {"school_name": strong, "program_name": "PhD", "school_tier": "strong"}, ctx)
            await dispatch("save_program", {"school_name": added.name, "program_name": "PhD", "school_tier": "solid"}, ctx)
            return strong, added.name

    strong, added = asyncio.run(setup())
    client = TestClient(app)
    by_tier = {s["name"]: s["tier"] for s in client.get("/api/schools?tier=strong").json()}
    assert by_tier.get(strong) == "strong" and set(by_tier.values()) == {"strong"}
    assert added in {s["name"] for s in client.get("/api/schools?tier=solid").json()}
    assert all(s["tier"] is None for s in client.get("/api/schools?tier=none").json())
    assert client.get("/api/schools?tier=elite").status_code == 422


def test_without_the_first_pass_the_agent_is_handed_the_index_entry(monkeypatch):
    from api.core.config import settings

    school = f"Index University {_uid()}"
    name = f"Prof Shannon {_uid()}"
    fake = OpenAlexCalls(monkeypatch, school)
    run_id, school_id, program_id = _run_at(TEST_USER_ID, school, UNRELATED)
    _research(run_id, program_id, name)

    monkeypatch.setattr(settings, "deterministic_research", False)
    seen = []

    async def fake_agent(system_prompt, user_message, ctx, **kwargs):
        seen.append((user_message, dict(ctx.works_by_author)))
        return {"final_text": "agent", "tool_log": [], "turns": 1, "usage": {}, "nudges": 0}

    monkeypatch.setattr(prospect_tasks, "run_agent_task", fake_agent)
    later_run, _, later_program = _run_at(TEST_USER_ID, school, ALIGNED, school_id=school_id)
    _research(later_run, later_program, name)

    message, works = seen[0]
    assert "professor index already has them" in message
    assert len(works) == 1 and len(fake.searches) == 1
