"""Seed (or remove) the invented demo account the product film is captured from.

    cd api && PYTHONPATH=. .venv/bin/python ../website/scripts/video/seed_demo.py <token-file>
    cd api && PYTHONPATH=. .venv/bin/python ../website/scripts/video/seed_demo.py --drop

Every person, school and paper here is invented. Seeding replaces any earlier
demo account and writes a refresh token to <token-file> for capture.mjs.
"""

import asyncio
import json
import sys
from datetime import date, timedelta

from sqlalchemy import delete, select

import api.main  # noqa: F401 - registers every model
from api.applications.models import Application
from api.assistant.models import AssistantConversation, AssistantMessage
from api.auth import models as auth_models
from api.auth import security, service
from api.candidates.models import CandidateScore, CandidateStatus
from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.index import sync as index_sync
from api.outreach.models import EmailDraft
from api.prospects.models import Paper, Professor, Program, RunSchool, School
from api.runs.models import ResearchTask, Run

EMAIL = "demo-film@graduator.example"
MODEL = "voyage-4"

INTEREST = (
    "Reinforcement learning for agile legged robots: training locomotion controllers in "
    "simulation that transfer safely to real quadrupeds."
)

SCHOOLS = [
    ("Northbridge University", "United Kingdom", "PhD in Robotics"),
    ("Lakeside Institute of Technology", "Switzerland", "Doctoral Programme in Robotics, Systems and Control"),
    ("Harbour University of Technology", "Netherlands", "PhD in Cognitive Robotics"),
    ("Calder University", "Sweden", "PhD in Autonomous Systems"),
    ("Eastport Technical University", "Germany", "Doctoral Programme in Informatics"),
    ("Valemont University", "Denmark", "PhD in Robotics and AI"),
]

# (name, school index, lab, score, rationale, papers[(title, year, citations, abstract)])
PROFESSORS = [
    (
        "Amara Reyes", 0, "Legged Robotics Lab", 0.82,
        "Her lab trains quadruped controllers in simulation and deploys them on hardware, which is the core of your "
        "statement. **Adaptive whole-body control for compliant legged robots** (2025) closes the sim-to-real gap with "
        "learned contact models, and her group publishes on safe exploration for locomotion.",
        [
            ("Adaptive whole-body control for compliant legged robots", 2025, 64,
             "We learn whole-body locomotion policies for quadrupeds in massively parallel simulation and transfer them "
             "to hardware with an adaptive contact model, recovering from slips and pushes without retraining."),
            ("Safe exploration for reinforcement learning on walking robots", 2024, 41,
             "A safety filter keeps a learning quadruped inside a certified region while it explores, cutting falls "
             "during on-robot fine-tuning by an order of magnitude."),
            ("Terrain-aware gait selection from proprioception", 2023, 88,
             "A recurrent policy infers terrain from joint feedback alone and switches gaits on stairs, gravel and snow."),
        ],
    ),
    (
        "Tobias Lindqvist", 3, "Robot Learning Group", 0.74,
        "Works on sample-efficient reinforcement learning for physical robots; **Model-based policy search for "
        "quadruped agility** (2024) is close to your interest in learning controllers that transfer.",
        [
            ("Model-based policy search for quadruped agility", 2024, 37,
             "Learned dynamics models let a quadruped acquire jumping and turning skills from twenty minutes of data."),
            ("Uncertainty-aware world models for legged locomotion", 2023, 52,
             "Ensembles of world models flag states where simulated training cannot be trusted on the real robot."),
        ],
    ),
    (
        "Ines Tanaka", 2, "Bio-inspired Robotics Lab", 0.69,
        "Studies animal-inspired locomotion and learned gaits. **Learning gaits from animal motion data** (2024) "
        "matches your focus on agile movement, though her work leans towards morphology.",
        [
            ("Learning gaits from animal motion data", 2024, 45,
             "Motion capture of dogs and goats seeds reinforcement learning for agile quadruped gaits."),
            ("Compliant legs for energy-efficient running robots", 2022, 73,
             "Series-elastic legs store and return energy, halving the cost of transport at speed."),
        ],
    ),
    (
        "Daniel Haddad", 4, "Safe Learning Group", 0.63,
        "Focuses on safety guarantees for learned controllers; **Certified safety for learned locomotion "
        "controllers** (2023) speaks to the safe-transfer part of your statement.",
        [
            ("Certified safety for learned locomotion controllers", 2023, 58,
             "Control barrier functions wrap a learned walking policy so it provably stays upright under bounded pushes."),
            ("Risk-aware reinforcement learning in the real world", 2024, 22,
             "A distributional critic lets robots trade reward against the chance of a costly failure."),
        ],
    ),
    (
        "Priya Raman", 1, "Robotic Systems Lab", 0.61,
        "Builds simulation tooling for robot learning; **GPU-parallel simulation for legged robots** (2024) is the "
        "kind of infrastructure your project would rely on.",
        [
            ("GPU-parallel simulation for legged robots", 2024, 120,
             "Thousands of simulated quadrupeds train in minutes on one GPU with domain randomisation for transfer."),
        ],
    ),
    (
        "Kwame Boateng", 5, "Embodied AI Lab", 0.57,
        "Works on embodied agents that learn from vision; overlaps with your interest where perception drives "
        "locomotion, in **Vision-guided locomotion over rough terrain** (2023).",
        [
            ("Vision-guided locomotion over rough terrain", 2023, 49,
             "Depth images feed a locomotion policy that plans footholds over gaps and stepping stones."),
        ],
    ),
    (
        "Elena Marchetti", 1, "Dynamic Systems Group", 0.52,
        "Optimal control for dynamic robots, with some learning; a partial fit through **Trajectory optimisation "
        "meets reinforcement learning** (2022).",
        [("Trajectory optimisation meets reinforcement learning", 2022, 66,
          "Optimised reference motions guide policy learning for acrobatic manoeuvres.")],
    ),
    (
        "Jonas Weber", 4, "Autonomous Machines Lab", 0.47,
        "Field robotics and navigation; locomotion is a smaller part of his work.",
        [("Long-range navigation for field robots", 2023, 31,
          "Robots plan kilometre-scale routes using satellite priors and local mapping.")],
    ),
    (
        "Sofia Alvarez", 0, "Human-Robot Interaction Lab", 0.44,
        "Human-robot interaction with some learning from demonstration; a weaker fit for locomotion.",
        [("Learning from demonstration for assistive robots", 2024, 19,
          "Assistive arms learn feeding motions from a handful of caregiver demonstrations.")],
    ),
    (
        "Hugo Laurent", 2, "Soft Robotics Group", 0.38,
        "Soft actuators and materials; little overlap with learned locomotion.",
        [("Pneumatic actuators for soft grippers", 2023, 27,
          "Printed pneumatic chambers give grippers adjustable stiffness.")],
    ),
]

APPLICATIONS = [
    (0, "applying", date(2026, 12, 15), [
        ("Online application form", True), ("Research proposal (1,500 words)", True), ("CV", True),
        ("Two academic references", False), ("Transcripts", False), ("English language test", False),
        ("Proposed supervisor", True),
    ], "Funded studentships cover fees and a stipend for 3.5 years."),
    (4, "submitted", date(2026, 11, 30), [
        ("Online application", True), ("Motivation letter", True), ("CV", True), ("Two references", True),
    ], ""),
    (1, "wishlist", date(2027, 1, 10), [
        ("Online application", False), ("Research statement", False), ("CV", False), ("Three references", False),
    ], "Doctoral positions are employed posts with a salary."),
    (2, "applying", date(2027, 1, 31), [
        ("Application portal", True), ("Cover letter", False), ("CV", True), ("Writing sample", False),
        ("Two references", False),
    ], ""),
    (3, "wishlist", date(2027, 2, 1), [
        ("Application form", False), ("Research plan", False), ("Degree certificates", False),
    ], ""),
]

DRAFT_SUBJECT = "Prospective PhD student: learned locomotion that transfers to real quadrupeds"
DRAFT_BODY = """Dear Professor Reyes,

I am applying to the PhD in Robotics at Northbridge for the 2027 intake, and your lab's work on learned locomotion is the reason I would like to study there.

Your paper on adaptive whole-body control for compliant legged robots, and in particular the way the learned contact model recovers from slips without retraining, is close to the question I want to work on: how to make policies trained in simulation transfer safely to real quadrupeds. Your follow-up on safe exploration suggests a natural next step, keeping on-robot fine-tuning inside a certified region.

In my master's project I trained quadruped gaits in parallel simulation and deployed them on a small robot, where most of my time went into closing the gap between simulated and real contacts. I have attached my CV and a short research statement.

Would you be taking new PhD students for the coming year? I would be glad to talk about whether my interests fit the lab's plans.

Kind regards,
Ama Mensah"""

CHAT_QUESTION = "Why is Amara Reyes my best fit?"
CHAT_ANSWER = """**Amara Reyes** is your strongest match, at **82%**.

- Her lab trains quadruped controllers in simulation and moves them onto real robots, which is exactly your question.
- *Adaptive whole-body control for compliant legged robots* (2025) closes the sim-to-real gap with a learned contact model.
- Her 2024 paper on safe exploration covers the safety side of your statement.

She is at Northbridge University, whose PhD in Robotics closes on **15 December**. Your draft to her is ready in the Outbox."""


def _log(steps: list[tuple[list[tuple[str, dict]], str]]) -> str:
    events = []
    for turn, (tools, note) in enumerate(steps):
        events += [{"turn": turn, "tool": tool, "input": params, "result_preview": "{}", "ok": True} for tool, params in tools]
        events.append({"kind": "turn", "turn": turn, "note": note})
    return json.dumps(events)


SCHOOL_LOG = _log([
    ([("search_web", {"query": "PhD robotics legged locomotion reinforcement learning Europe"}),
      ("search_web", {"query": "doctoral programme robot learning quadruped"})],
     "Found strong legged-robotics groups in the UK, Switzerland, the Netherlands, Sweden, Germany and Denmark."),
    ([("fetch_page", {"url": "https://www.northbridge.example/robotics/phd"}),
      ("fetch_page", {"url": "https://www.lakeside.example/doctoral/robotics"}),
      ("fetch_page", {"url": "https://www.harbour.example/cognitive-robotics"})],
     "Confirmed three programmes with funded places and faculty working on learned locomotion."),
    ([("fetch_page", {"url": "https://www.calder.example/autonomous-systems"}),
      ("fetch_page", {"url": "https://www.eastport.example/informatics/doctoral"}),
      ("fetch_page", {"url": "https://www.valemont.example/robotics-ai"})],
     "Three more confirmed. Each lists faculty pages, so professor research can start."),
    ([("save_program", {"name": name}) for _, _, name in SCHOOLS],
     "Saved six programmes and queued faculty research at each school."),
])


def _professor_log(name: str, score: float) -> str:
    return _log([
        ([("find_openalex_author", {"name": name}), ("get_author_works", {"limit": 50, "years": 5})],
         f"Found {name} and read their recent publications."),
        ([("score_alignment", {}), ("save_professor_record", {"name": name})],
         f"Scored {round(score * 100)}% against your interests and saved the match."),
    ])


async def drop(session) -> None:
    user = (await session.execute(select(auth_models.User).where(auth_models.User.email == EMAIL))).scalar_one_or_none()
    if user is None:
        return
    await session.execute(delete(auth_models.RefreshToken).where(auth_models.RefreshToken.user_id == user.id))
    await session.delete(user)
    await session.commit()


async def seed(token_file: str) -> None:
    async with SessionLocal() as session:
        await drop(session)
        now = utcnow_naive()
        user = auth_models.User(
            email=EMAIL, password_hash=security.hash_password("demo-film-not-a-real-account"),
            display_name="Ama Mensah", email_verified_at=now, terms_accepted_at=now, plan="pro", plan_selected_at=now,
            plan_expires_at=now + timedelta(days=30),
        )
        session.add(user)
        await session.flush()
        uid = user.id

        run = Run(
            user_id=uid, region="Europe", field="Robotics / Reinforcement Learning", degree_level="PhD",
            interest_statement=INTEREST, status="done", max_programs=6, max_professors=60,
        )
        session.add(run)
        await session.flush()
        session.add(ResearchTask(
            user_id=uid, run_id=run.id, task_type="discover_programs", target_id=run.id,
            target_name="Research schools", status="done", log=SCHOOL_LOG, turns=4,
            input_tokens=61_000, output_tokens=4_200, started_at=now - timedelta(minutes=34),
            finished_at=now - timedelta(minutes=21),
        ))

        programs = []
        for name, country, program_name in SCHOOLS:
            school = School(user_id=uid, run_id=run.id, name=name, country=country)
            session.add(school)
            await session.flush()
            session.add(RunSchool(run_id=run.id, school_id=school.id))
            program = Program(user_id=uid, school_id=school.id, name=program_name)
            session.add(program)
            await session.flush()
            programs.append(program)

        candidates = {}
        by_school: dict[int, list[dict]] = {}
        for name, school_index, lab, score, rationale, papers in PROFESSORS:
            professor = Professor(
                user_id=uid, program_id=programs[school_index].id, name=name, lab_name=lab,
                bio=f"{name} leads the {lab} at {SCHOOLS[school_index][0]}.",
            )
            session.add(professor)
            await session.flush()
            for title, year, citations, abstract in papers:
                session.add(Paper(
                    user_id=uid, professor_id=professor.id, title=title, abstract=abstract, year=year,
                    citations=citations, publication_type="article", coauthors=[],
                ))
            candidate = CandidateScore(
                user_id=uid, run_id=run.id, professor_id=professor.id, similarity_score=score,
                scoring_method="embedding", embedding_model=MODEL, rationale=rationale,
                status=CandidateStatus.scored,
            )
            session.add(candidate)
            session.add(ResearchTask(
                user_id=uid, run_id=run.id, task_type="research_one_professor", target_id=professor.id,
                target_name=name, status="done", log=_professor_log(name, score), turns=2,
                input_tokens=9_000, output_tokens=700, started_at=now - timedelta(minutes=20),
                finished_at=now - timedelta(minutes=12),
            ))
            await session.flush()
            candidates[name] = (candidate, professor)
            by_school.setdefault(school_index, []).append({
                "name": name, "candidate_id": candidate.id, "professor_id": professor.id,
                "school": SCHOOLS[school_index][0],
            })

        best, best_professor = candidates["Amara Reyes"]
        draft = EmailDraft(user_id=uid, candidate_id=best.id, subject=DRAFT_SUBJECT, body=DRAFT_BODY)
        session.add(draft)
        best.status = CandidateStatus.drafted

        for school_index, status, deadline, requirements, offer in APPLICATIONS:
            school, country, program_name = SCHOOLS[school_index]
            session.add(Application(
                user_id=uid, school=school, program=program_name, degree_type="phd", location=country,
                requirements=[{"label": label, "done": done} for label, done in requirements], offer=offer,
                deadline=deadline.isoformat(), deadline_date=deadline, status=status, professors=by_school.get(school_index, [])[:2],
                run_id=run.id, program_id=programs[school_index].id,
            ))

        conversation = AssistantConversation(user_id=uid, title="Best fit for legged robots")
        session.add(conversation)
        await session.flush()
        session.add(AssistantMessage(user_id=uid, conversation_id=conversation.id, role="user", content=CHAT_QUESTION))
        session.add(AssistantMessage(
            user_id=uid, conversation_id=conversation.id, role="assistant", content=CHAT_ANSWER,
            tool_calls_json=json.dumps([
                {"turn": 0, "tool": "get_candidate", "input": {"candidate_id": best.id}, "result_preview": "{}", "ok": True},
                {"turn": 0, "tool": "list_applications", "input": {}, "result_preview": "{}", "ok": True},
            ]),
        ))
        await session.commit()

        for candidate, _ in candidates.values():
            async with index_sync.guarded(session, f"candidate {candidate.id}"):
                await index_sync.sync_candidate_id(session, candidate.id)
        await session.commit()

        pair = await service.issue_pair(session, await session.get(auth_models.User, uid))
        with open(token_file, "w") as f:
            f.write(pair["refresh_token"])
        print(json.dumps({
            "run": run.id, "best_candidate": best.id, "best_professor": best_professor.id,
            "conversation": conversation.id, "draft": draft.id,
        }))


async def main() -> None:
    if sys.argv[1:] == ["--drop"]:
        async with SessionLocal() as session:
            await drop(session)
        return
    await seed(sys.argv[1])


asyncio.run(main())
