import asyncio

from api.agent.tools import ToolContext, dispatch
from api.candidates.models import CandidateScore, CandidateStatus
from api.core.db import SessionLocal
from api.outreach import tasks as outreach_tasks
from api.outreach.draft_check import verify_draft
from api.prospects.models import Paper, Professor
from api.runs.models import Run
from tests.conftest import TEST_USER_ID
from tests.test_budgets import _make_program, _make_run

TITLE = "Learning agile locomotion for legged robots"
GOOD = (
    "Dear Professor Lee,\n\nYour paper Learning agile locomotion for legged robots "
    "shaped how I think about sim-to-real transfer. I am [your current degree and "
    "university] and hope to join your group as a PhD student. Are you taking "
    "students next cycle?\n\nBest,\n[your name]"
)


def test_verify_draft_rules():
    assert verify_draft("Hi", GOOD, [TITLE]) is None
    assert "stored papers" in verify_draft("Hi", "Dear Prof, I like robots.", [TITLE])
    long_body = GOOD + " word" * 260
    assert "250" in verify_draft("Hi", long_body, [TITLE])
    assert "placeholders" in verify_draft("Hi", GOOD + " {student_name}", [TITLE])
    # [brackets] are the sanctioned placeholder for unknown facts.
    assert verify_draft("Hi", GOOD, [TITLE]) is None
    # User-requested drafts skip the citation rule only.
    assert verify_draft("Hi", "Short follow-up.", None) is None
    assert "placeholders" in verify_draft("Hi", "{x}", None)


def _candidate(run_id, program_id) -> str:
    async def go():
        async with SessionLocal() as session:
            prof = Professor(user_id=TEST_USER_ID, program_id=program_id, name="Lee")
            session.add(prof)
            await session.flush()
            session.add(Paper(user_id=TEST_USER_ID, professor_id=prof.id, title=TITLE))
            cand = CandidateScore(
                user_id=TEST_USER_ID,
                run_id=run_id,
                professor_id=prof.id,
                similarity_score=0.9,
                rationale=f"Cites {TITLE}.",
                status=CandidateStatus.scored,
            )
            session.add(cand)
            await session.commit()
            return cand.id

    return asyncio.run(go())


def test_agent_save_refuses_uncited_and_overlong_drafts():
    run_id = _make_run()
    _, program_id = _make_program(run_id)
    candidate_id = _candidate(run_id, program_id)

    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            ctx = ToolContext(session=session, run=run)
            uncited = await dispatch(
                "save_email_draft",
                {
                    "candidate_id": candidate_id,
                    "subject": "PhD",
                    "body": "I like robots.",
                },
                ctx,
            )
            overlong = await dispatch(
                "save_email_draft",
                {
                    "candidate_id": candidate_id,
                    "subject": "PhD",
                    "body": GOOD + " x" * 300,
                },
                ctx,
            )
            ok = await dispatch(
                "save_email_draft",
                {"candidate_id": candidate_id, "subject": "PhD", "body": GOOD},
                ctx,
            )
            return uncited, overlong, ok

    uncited, overlong, ok = asyncio.run(go())
    assert "stored papers" in uncited["error"]
    assert "250" in overlong["error"]
    assert ok["status"] == "drafted"


def test_brief_has_degree_level_and_known_facts(monkeypatch):
    run_id = _make_run()
    _, program_id = _make_program(run_id)
    candidate_id = _candidate(run_id, program_id)
    seen = {}

    async def fake_run_agent_task(system_prompt, user_message, ctx, **kwargs):
        seen["brief"] = user_message
        seen["system"] = system_prompt
        return {"final_text": "", "tool_log": [], "turns": 0, "usage": {}}

    monkeypatch.setattr(outreach_tasks, "run_agent_task", fake_run_agent_task)

    class Task:
        id = "t1"
        target_id = candidate_id

    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            await outreach_tasks.run_draft_email(session, Task(), run)

    asyncio.run(go())
    assert "Seeking: PhD admission" in seen["brief"]
    assert "Known facts about the student" in seen["brief"]
    assert "[bracketed placeholders]" in seen["brief"]
    assert "Never invent a degree" in seen["system"]


def test_invented_background_is_refused_even_with_a_citation():
    from types import SimpleNamespace

    from api.outreach.draft_check import known_facts_for

    run = SimpleNamespace(
        degree_level="phd",
        field="robotics",
        interest_statement="Legged locomotion and sim-to-real transfer.",
    )
    facts = known_facts_for(run)
    invented = [
        "I hold an MSc in Robotics with a GPA of 3.9/4.0.",
        "I graduated with first-class honours.",
        "I have published two papers on locomotion.",
        "I have three years of industry experience.",
        "I work at a robotics startup.",
    ]
    for claim in invented:
        body = GOOD.replace("I am [your current degree and", f"{claim} I am [your")
        error = verify_draft("PhD", body, [TITLE], facts)
        assert error and "never gave you" in error, claim
    assert verify_draft("PhD", GOOD, [TITLE], facts) is None
    own_words = GOOD + " I care about sim-to-real transfer."
    assert verify_draft("PhD", own_words, [TITLE], facts) is None


def test_agent_save_refuses_invented_gpa():
    run_id = _make_run()
    _, program_id = _make_program(run_id)
    candidate_id = _candidate(run_id, program_id)
    body = GOOD.replace(
        "I am [your current degree and", "My GPA is 3.9/4.0. I am [your"
    )

    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            return await dispatch(
                "save_email_draft",
                {"candidate_id": candidate_id, "subject": "PhD", "body": body},
                ToolContext(session=session, run=run),
            )

    assert "never gave you" in asyncio.run(go())["error"]


def _facts():
    from types import SimpleNamespace

    from api.outreach.draft_check import known_facts_for

    return known_facts_for(
        SimpleNamespace(
            degree_level="phd",
            field="robotics",
            interest_statement=(
                "Legged locomotion and sim-to-real transfer; my MSc work at "
                "KNUST was on quadruped control."
            ),
        )
    )


def _with(sentence: str) -> str:
    return GOOD.replace("I am [your current degree and", f"{sentence} I am [your")


def test_second_round_claims_are_refused():
    from api.outreach.draft_check import target_names_for

    targets = target_names_for("Massachusetts Institute of Technology", "Lee")
    invented = [
        "I am a Stanford student.",
        "As a University of Ghana graduate, I bring rigour.",
        "I studied at Imperial College London.",
        "I am a research assistant at Oxford.",
        "I finished with a 3.9 average.",
        "My average was 3.8 across all modules.",
        "I graduated with an 85% average.",
        "I was in the top 5% of my class.",
        "The student holds an MSc from ETH Zurich.",
        "The applicant has a GPA of 3.9.",
        "She has three years of research experience.",
        "I hope to join your lab as a former Stanford student.",
        "I attend Stanford University.",
        "My alma mater is Stanford University.",
        "Stanford is where I did my undergrad.",
        "I did my undergrad at Stanford.",
        "I earned a BSc from the University of Lagos.",
        "I scored in the 98th percentile.",
        "I was first in my class.",
        "I spent last summer at Google DeepMind.",
    ]
    for claim in invented:
        error = verify_draft("PhD", _with(claim), [TITLE], _facts(), targets)
        assert error and "never gave you" in error, claim


def test_second_round_legit_sentences_pass():
    from api.outreach.draft_check import target_names_for

    targets = target_names_for("Massachusetts Institute of Technology", "Lee")
    legit = [
        "I hold your work in high regard.",
        "I studied your paper closely.",
        "I would love to join your lab at MIT as a PhD student.",
        "I hope to work at a lab like yours.",
        "I am a final-year student at [your university].",
        "I am applying to the Massachusetts Institute of Technology as a PhD student.",
        # Grounded: the interest statement names the student's own school.
        "My MSc work at KNUST was on quadruped control.",
        "I studied at KNUST.",
        "Your group reported a 3.9 average speed-up.",
        "I enjoyed your talk at NeurIPS.",
        "I have followed the Lee group's work for a while.",
        "I think Learning agile locomotion is a model for sim-to-real work.",
        "I care most about legged locomotion.",
        "I plan to apply for the Fall 2026 intake.",
    ]
    for sentence in legit:
        assert (
            verify_draft("PhD", _with(sentence), [TITLE], _facts(), targets) is None
        ), sentence


def test_agent_save_refuses_ungrounded_affiliation():
    run_id = _make_run()
    _, program_id = _make_program(run_id)
    candidate_id = _candidate(run_id, program_id)

    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            return await dispatch(
                "save_email_draft",
                {
                    "candidate_id": candidate_id,
                    "subject": "PhD",
                    "body": _with("I am a Stanford student."),
                },
                ToolContext(session=session, run=run),
            )

    assert "affiliation" in asyncio.run(go())["error"]
