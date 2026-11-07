"""TypeSafe rationale-verifier tests (Jev client stubbed - no network)."""

import asyncio

from api.agent.tools import ToolContext, dispatch
from api.candidates import verification
from api.core.config import settings
from api.core.db import SessionLocal
from api.prospects.models import Program, RunSchool, School
from api.runs.models import Run
from tests.conftest import TEST_USER_ID
from tests.grounding_helpers import ground


class _FakeAnswer:
    def __init__(self, choice, confidence):
        self.choice = choice
        self.confidence = confidence
        self.probabilities = {choice: confidence}


class _FakeResponse:
    def __init__(self, answer):
        self.answers = {"citation": answer}
        self.model = "jev-test"


def _fake_client_class(answer=None, exc=None, constructed=None, calls=None):
    class FakeClient:
        def __init__(self, api_key=None):
            if constructed is not None:
                constructed.append(api_key)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def system_one(self, *, state, questions, model):
            if calls is not None:
                calls.append({"state": state, "model": model, "questions": questions})
            if exc is not None:
                raise exc
            return _FakeResponse(answer)

    return FakeClient


def _enable(monkeypatch, settings):
    monkeypatch.setattr(settings, "typesafe_rationale_check", True)
    monkeypatch.setattr(settings, "typesafe_api_key", "test-key")
    monkeypatch.setattr(settings, "typesafe_model", "jev-test")
    monkeypatch.setattr(settings, "typesafe_auto_accept", 0.8)


def test_verified_auto_accept(monkeypatch):

    monkeypatch.setattr(
        verification,
        "AsyncTypeSafeClient",
        _fake_client_class(_FakeAnswer("supports", 0.93)),
    )
    out = asyncio.run(
        verification.check_rationale_citation(
            "their RL planners",
            [{"title": "T", "abstract": "A"}],
            api_key="k",
            model="jev-test",
            auto_accept=0.8,
        )
    )
    assert out == {
        "verdict": "verified",
        "confidence": 0.93,
        "auto": True,
        "model": "jev-test",
    }


def test_contradicted_and_low_confidence_not_auto(monkeypatch):

    monkeypatch.setattr(
        verification,
        "AsyncTypeSafeClient",
        _fake_client_class(_FakeAnswer("contradicts", 0.99)),
    )
    out = asyncio.run(
        verification.check_rationale_citation(
            "x", [], api_key="k", model="m", auto_accept=0.8
        )
    )
    assert out["verdict"] == "contradicted"
    assert out["auto"] is False

    monkeypatch.setattr(
        verification,
        "AsyncTypeSafeClient",
        _fake_client_class(_FakeAnswer("supports", 0.5)),
    )
    out = asyncio.run(
        verification.check_rationale_citation(
            "x", [], api_key="k", model="m", auto_accept=0.8
        )
    )
    assert out["verdict"] == "verified"
    assert out["auto"] is False


def test_disabled_or_unkeyed_returns_none(monkeypatch):

    constructed = []
    monkeypatch.setattr(
        verification,
        "AsyncTypeSafeClient",
        _fake_client_class(_FakeAnswer("supports", 0.99), constructed=constructed),
    )

    monkeypatch.setattr(settings, "typesafe_rationale_check", False)
    monkeypatch.setattr(settings, "typesafe_api_key", "test-key")
    assert asyncio.run(verification.maybe_verify_rationale({})) is None

    monkeypatch.setattr(settings, "typesafe_rationale_check", True)
    monkeypatch.setattr(settings, "typesafe_api_key", "")
    assert asyncio.run(verification.maybe_verify_rationale({})) is None
    assert constructed == []


def test_service_failure_returns_none(monkeypatch):

    _enable(monkeypatch, settings)
    monkeypatch.setattr(
        verification,
        "AsyncTypeSafeClient",
        _fake_client_class(exc=RuntimeError("down")),
    )
    assert asyncio.run(verification.maybe_verify_rationale({"rationale": "x"})) is None


def _make_run_and_program():

    async def setup():
        async with SessionLocal() as session:
            run = Run(user_id=TEST_USER_ID, 
                region="U",
                field="f",
                degree_level="phd",
                interest_statement="x",
                status="running",
            )
            session.add(run)
            await session.flush()
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run.id)], name="S")
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name="P")
            session.add(program)
            await session.commit()
            return run.id, program.id

    return asyncio.run(setup())


def _paraphrased_input():
    return {
        "name": "Prof Paraphrase",
        "papers": [
            {"title": "Deep reinforcement learning for legged locomotion control"}
        ],
        "similarity_score": 0.9,
        "rationale": "Their ongoing work on learning-based walking controllers is a strong match.",
    }


def test_paraphrase_allowed_by_jev(monkeypatch):

    _enable(monkeypatch, settings)
    monkeypatch.setattr(
        verification,
        "AsyncTypeSafeClient",
        _fake_client_class(_FakeAnswer("supports", 0.91)),
    )
    run_id, program_id = _make_run_and_program()

    async def save():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            return await dispatch("save_professor_record", ground(ctx, _paraphrased_input()), ctx)

    out = asyncio.run(save())
    assert "candidate_id" in out
    assert out["verification"]["method"] == "typesafe"
    assert out["verification"]["verdict"] == "verified"


def test_jev_disallow_keeps_refusal(monkeypatch):

    _enable(monkeypatch, settings)
    monkeypatch.setattr(
        verification,
        "AsyncTypeSafeClient",
        _fake_client_class(_FakeAnswer("says_nothing", 0.4)),
    )
    run_id, program_id = _make_run_and_program()

    async def save():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            return await dispatch("save_professor_record", ground(ctx, _paraphrased_input()), ctx)

    out = asyncio.run(save())
    assert "error" in out
    assert "semantic check: unsupported" in out["error"]


def test_exact_citation_needs_no_client(monkeypatch):

    _enable(monkeypatch, settings)
    constructed = []
    monkeypatch.setattr(
        verification,
        "AsyncTypeSafeClient",
        _fake_client_class(_FakeAnswer("supports", 0.99), constructed=constructed),
    )
    run_id, program_id = _make_run_and_program()

    async def save():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            payload = _paraphrased_input()
            payload["rationale"] = (
                "Direct match to Deep reinforcement learning for legged locomotion control."
            )
            return await dispatch("save_professor_record", ground(ctx, payload), ctx)

    out = asyncio.run(save())
    assert "candidate_id" in out
    assert "verification" not in out
    assert constructed == []


class _Answer:
    def __init__(self, **fields):
        self.__dict__.update(fields)


def _jev(monkeypatch, answer=None, exc=None, calls=None):
    async def ask(state, question):
        if calls is not None:
            calls.append(state)
        if exc is not None:
            raise exc
        return answer

    monkeypatch.setattr(settings, "typesafe_api_key", "test-key")
    monkeypatch.setattr(settings, "typesafe_auto_accept", 0.8)
    monkeypatch.setattr(verification, "_ask", ask)


AUTHORS = [
    {"openalex_id": "A1", "display_name": "Ana Li", "institutions": ["Test U"], "topics": ["Robotics"]},
    {"openalex_id": "A2", "display_name": "Ana Li", "institutions": ["Test U"], "topics": ["Oncology"]},
]


def test_jev_picks_the_author_it_is_confident_about(monkeypatch):
    monkeypatch.setattr(settings, "typesafe_author_pick", True)
    _jev(monkeypatch, _Answer(choice="author_0", confidence=0.92))
    assert asyncio.run(verification.pick_author("Ana Li", "Test U", "Robotics", AUTHORS)) == AUTHORS[0]


def test_an_unsure_or_none_pick_leaves_it_to_the_agent(monkeypatch):
    monkeypatch.setattr(settings, "typesafe_author_pick", True)
    _jev(monkeypatch, _Answer(choice="author_1", confidence=0.6))
    assert asyncio.run(verification.pick_author("Ana Li", "Test U", "Robotics", AUTHORS)) is None
    _jev(monkeypatch, _Answer(choice="none", confidence=0.99))
    assert asyncio.run(verification.pick_author("Ana Li", "Test U", "Robotics", AUTHORS)) is None
    _jev(monkeypatch, exc=RuntimeError("outage"))
    assert asyncio.run(verification.pick_author("Ana Li", "Test U", "Robotics", AUTHORS)) is None


def test_judgments_are_off_until_switched_on(monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "typesafe_author_pick", False)
    monkeypatch.setattr(settings, "typesafe_fit_rating", False)
    _jev(monkeypatch, _Answer(choice="author_0", confidence=0.99, score=4.0), calls=calls)
    assert asyncio.run(verification.pick_author("Ana Li", "Test U", None, AUTHORS)) is None
    assert asyncio.run(verification.rate_fit("robots", [{"title": "T"}])) is None
    assert calls == []


def test_a_fit_rating_reads_as_level_label_and_score(monkeypatch):
    monkeypatch.setattr(settings, "typesafe_fit_rating", True)
    _jev(monkeypatch, _Answer(score=2.6, confidence=0.85))
    fit = asyncio.run(verification.rate_fit("robot learning", [{"title": "Legged robots", "abstract": "walking"}]))
    assert fit == {"level": 2.6, "label": "strong", "score": 0.65, "confidence": 0.85}
