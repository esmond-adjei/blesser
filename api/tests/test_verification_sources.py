"""Every response is recorded and served through a mock transport; nothing reaches the network."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from api.agent.llm.base import LLMResponse, ToolCall
from api.agent.tools.context import ToolContext
from api.agent.tools.dispatch import HANDLERS
from api.candidates import scoring
from api.candidates.models import CandidateScore
from api.core.config import settings
from api.core.db import SessionLocal
from api.prospects import grounding, openalex, profile_ids, source_http, sources
from api.prospects import tasks as prospect_tasks
from api.prospects.models import Paper, Professor, Program, RunSchool, School
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID

pytestmark = pytest.mark.verification_sources

THIS_YEAR = datetime.now(UTC).year
FUTURE = (datetime.now(UTC) + timedelta(days=400)).date().isoformat()


def _school_name() -> str:
    return f"Graduator Test Institute {uuid.uuid4().hex[:6]}"


def dblp_search(name: str, school: str) -> dict:
    return {
        "result": {
            "hits": {
                "@total": "2",
                "hit": [
                    {"info": {"author": f"{name} 0001", "url": "https://dblp.org/pid/12/3456",
                              "notes": {"note": {"@type": "affiliation", "text": f"{school}, Testville, USA"}}}},
                    {"info": {"author": f"{name} 0002", "url": "https://dblp.org/pid/99/1",
                              "notes": {"note": [{"@type": "affiliation", "text": "Elsewhere University, UK"}]}}},
                ]
            }
        }
    }  # fmt: skip


def dblp_person(name: str, school: str, pid: str = "12/3456") -> str:
    return f"""<?xml version="1.0" encoding="US-ASCII"?>
<dblpperson name="{name} 0001" pid="{pid}" n="3">
<person key="homepages/{pid}" mdate="2024-01-01">
<author pid="{pid}">{name} 0001</author>
<note type="affiliation">{school}, Testville, USA</note>
<url>https://orcid.org/0000-0002-1825-0097</url>
</person>
<r><inproceedings key="conf/x/A{THIS_YEAR}" mdate="2024-01-01"><author pid="{pid}">{name}</author>
<title>Robot learning from <i>human</i> demonstrations.</title><year>{THIS_YEAR}</year>
<booktitle>ICRA</booktitle><ee>https://doi.org/10.1/robot</ee></inproceedings></r>
<r><article key="journals/x/B{THIS_YEAR - 1}" mdate="2024-01-01"><author pid="{pid}">{name}</author>
<title>Sample-efficient policy search for manipulation.</title><year>{THIS_YEAR - 1}</year>
<journal>T-RO</journal></article></r>
<r><article key="journals/x/Old" mdate="2024-01-01"><author pid="{pid}">{name}</author>
<title>An old paper on databases.</title><year>1999</year><journal>VLDB</journal></article></r>
</dblpperson>"""


def nih_projects(name: str, school: str) -> dict:
    first, last = name.split()[0], name.split()[-1]
    return {
        "meta": {"total": 2},
        "results": [
            {"appl_id": 111, "project_num": "5R01GM123456-04", "fiscal_year": THIS_YEAR,
             "project_title": "Single-cell maps of tissue regeneration",
             "abstract_text": "We map regeneration in single cells across tissues.",
             "organization": {"org_name": school.upper()},
             "principal_investigators": [{"profile_id": 777, "first_name": first.upper(),
                                          "last_name": last.upper(), "full_name": name}],
             "project_start_date": f"{THIS_YEAR - 2}-04-01T12:00:00Z", "project_end_date": f"{FUTURE}T12:00:00Z",
             "project_detail_url": "https://reporter.nih.gov/project-details/111"},
            {"appl_id": 222, "project_num": "1R21AA000001-01", "fiscal_year": THIS_YEAR - 1,
             "project_title": "Someone else's grant", "abstract_text": "Unrelated.",
             "organization": {"org_name": "OTHER STATE UNIVERSITY"},
             "principal_investigators": [{"profile_id": 888, "first_name": first.upper(),
                                          "last_name": last.upper(), "full_name": name}],
             "project_start_date": f"{THIS_YEAR - 3}-01-01T00:00:00Z", "project_end_date": f"{FUTURE}T00:00:00Z"},
        ],
    }  # fmt: skip


def nsf_awards(name: str, school: str) -> dict:
    first, last = name.split()[0], name.split()[-1]
    return {
        "response": {
            "award": [
                {"id": "2112345", "title": "CAREER: Learning robots", "abstractText": "Robots that learn.",
                 "awardeeName": school, "piFirstName": first, "piLastName": last,
                 "startDate": f"09/01/{THIS_YEAR - 1}", "expDate": f"08/31/{THIS_YEAR + 3}"},
            ]
        }
    }  # fmt: skip


class Recorder:
    """A mock transport for DBLP, NIH and NSF that records every request."""

    def __init__(self, name: str, school: str, **overrides):
        self.name, self.school = name, school
        self.sent: list[httpx.Request] = []
        self.overrides = overrides

    def hosts(self) -> list[str]:
        return [r.url.host for r in self.sent]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        host, path = request.url.host, request.url.path
        source = {
            "dblp.org": "dblp", "api.reporter.nih.gov": "nih", "api.nsf.gov": "nsf",
            "pub.orcid.org": "orcid", "api.semanticscholar.org": "semantic_scholar",
        }[host]  # fmt: skip
        override = self.overrides.get(source)
        if override is not None:
            return override(request) if callable(override) else override
        if source == "orcid":
            # Nobody by default: tests of ORCID itself override it.
            return httpx.Response(200, json={"expanded-result": None, "num-found": 0})
        if source == "semantic_scholar":
            ids = json.loads(request.content or b"{}").get("ids") or []
            return httpx.Response(200, json=[None for _ in ids])
        if source == "dblp" and path.startswith("/search/author"):
            return httpx.Response(200, json=dblp_search(self.name, self.school))
        if source == "dblp":
            return httpx.Response(200, text=dblp_person(self.name, self.school))
        if source == "nih":
            return httpx.Response(200, json=nih_projects(self.name, self.school))
        return httpx.Response(200, json=nsf_awards(self.name, self.school))


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setattr(
        settings, "source_min_interval_seconds",
        {"dblp": 0, "nih": 0, "nsf": 0, "orcid": 0, "semantic_scholar": 0},
    )  # fmt: skip

    def install(recorder: Recorder) -> Recorder:
        client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
        monkeypatch.setattr(source_http, "client", lambda: client)
        return recorder

    return install


def _setup(school_name: str, prof: str, field: str = "machine learning", program_name: str = "Computer Science",
           country: str = "United States"):  # fmt: skip
    async def go():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID, region="US", field=field, degree_level="phd",
                interest_statement="robot learning", status="running", max_professors=100,
            )  # fmt: skip
            session.add(run)
            await session.flush()
            school = School(
                user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run.id)], name=school_name,
                country=country, website_url="https://www.gti.example.edu",
            )  # fmt: skip
            session.add(school)
            await session.flush()
            program = Program(
                user_id=TEST_USER_ID, school_id=school.id, name=program_name,
                department_url="https://cs.gti.example.edu/people",
            )  # fmt: skip
            session.add(program)
            await session.flush()
            from api.applications.models import Application

            session.add(Application(user_id=TEST_USER_ID, run_id=run.id, school=school_name))
            task = ResearchTask(
                run_id=run.id, user_id=TEST_USER_ID, task_type="research_one_professor",
                target_id=program.id, target_name=prof, status=TaskStatus.running,
            )  # fmt: skip
            session.add(task)
            await session.commit()
            return run.id, program.id, task.id

    return asyncio.run(go())


def _nobody_on_openalex(monkeypatch, calls=None):
    async def find_author(name, hint=None, **_):
        if calls is not None:
            calls.append(name)
        return []

    monkeypatch.setattr(openalex, "find_author", find_author)


def _score(monkeypatch, value=0.6):
    async def score(ctx, interest, texts):
        return {"score": value, "best_index": 0, "all_scores": [value] * len(texts), "method": "embedding"}

    monkeypatch.setattr(scoring, "score_interest_for_ctx_async", score)


class BriefSaver:
    """Plays the one-call save from the brief, whatever the author's source."""

    def __init__(self):
        self.briefs = []

    async def chat(self, messages, system, tools, max_tokens=4096):
        brief = messages[0]["content"]
        self.briefs.append(brief)
        name = brief.split("Professor: ", 1)[1].split("\n", 1)[0]
        marker = "Author id (pass it as openalex_id): " if "Author id" in brief else "OpenAlex author: "
        author = brief.split(marker, 1)[1].split(" ", 1)[0]
        score = float(brief.split("similarity_score ", 1)[1].split(" ", 1)[0])
        title = brief.split("already fetched and scored:\n- \"", 1)[1].split('"', 1)[0]
        return LLMResponse(
            text="",
            tool_calls=[
                ToolCall(
                    id="s1",
                    name="save_professor_record",
                    arguments={
                        "name": name,
                        "openalex_id": author,
                        "papers": [{"title": title}],
                        "similarity_score": score,
                        "rationale": f"{title} is on the student's topic.",
                    },
                )
            ],
        )


def _research(monkeypatch, run_id, task_id, model=None):
    import api.agent.orchestrator as orch

    if model is not None:
        monkeypatch.setattr(orch, "get_provider", lambda **_: model)

    async def go():
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            run = await session.get(Run, run_id)
            return await prospect_tasks.run_research_one_professor(session, task, run)

    return asyncio.run(go())


def _saved(program_id):
    async def go():
        async with SessionLocal() as session:
            prof = (
                await session.execute(select(Professor).where(Professor.program_id == program_id))
            ).scalar_one()
            papers = (await session.execute(select(Paper).where(Paper.professor_id == prof.id))).scalars().all()
            candidate = (
                await session.execute(select(CandidateScore).where(CandidateScore.professor_id == prof.id))
            ).scalar_one()
            return prof, papers, candidate

    return asyncio.run(go())


@pytest.mark.pipeline
def test_dblp_verifies_a_cs_professor_openalex_does_not_know(monkeypatch, transport):
    school = _school_name()
    recorder = transport(Recorder("Jane Smith", school))
    _nobody_on_openalex(monkeypatch)
    _score(monkeypatch)
    run_id, program_id, task_id = _setup(school, "Jane Smith")
    model = BriefSaver()
    _research(monkeypatch, run_id, task_id, model)

    assert len(model.briefs) == 1
    brief = model.briefs[0]
    assert "dblp:12/3456" in brief and "verified via DBLP" in brief and "titles only" in brief
    # NIH/NSF weren't needed to verify (grants are still checked as a funding signal).
    assert [r.url.path for r in recorder.sent if r.url.host == "dblp.org"] == [
        "/search/author/api",
        "/pid/12/3456.xml",
    ]
    prof, papers, candidate = _saved(program_id)
    assert prof.openalex_id is None
    assert {"label": "DBLP", "url": "https://dblp.org/pid/12/3456"} in prof.socials
    assert [p.title for p in papers] == ["Robot learning from human demonstrations"]
    assert papers[0].url == "https://doi.org/10.1/robot" and papers[0].abstract is None
    assert "Verified via DBLP" in candidate.rationale and "lower confidence" in candidate.rationale
    assert candidate.similarity_score == pytest.approx(0.6)


@pytest.mark.pipeline
def test_a_repeated_source_save_is_deduplicated(monkeypatch, transport):
    school = _school_name()
    transport(Recorder("Jane Smith", school))
    _nobody_on_openalex(monkeypatch)
    _score(monkeypatch)
    run_id, program_id, _task_id = _setup(school, "Jane Smith")

    async def go():
        async with SessionLocal() as session:
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=await session.get(Run, run_id), program=program)
            found = await HANDLERS["find_openalex_author"]({"name": "Jane Smith"}, ctx)
            scored = await HANDLERS["score_alignment"]({"openalex_id": "dblp:12/3456"}, ctx)
            payload = {
                "name": "Jane Smith",
                "openalex_id": "dblp:12/3456",
                "papers": [{"title": scored["top_works"][0]["title"]}],
                "similarity_score": scored["score"],
                "rationale": f"{scored['top_works'][0]['title']} fits.",
            }
            first = await HANDLERS["save_professor_record"](dict(payload), ctx)
            second = await HANDLERS["save_professor_record"](dict(payload), ctx)
            return found, scored, first, second

    found, scored, first, second = asyncio.run(go())
    assert found["candidates"][0]["source"] == "dblp"
    assert "already fetched" in found["note"]
    assert scored["confidence"].startswith("lower")
    assert "candidate_id" in first
    assert second["deduped"] is True and second["professor_id"] == first["professor_id"]


@pytest.mark.pipeline
def test_grants_verify_while_the_openalex_breaker_is_open(monkeypatch, transport):
    school = _school_name()
    recorder = transport(Recorder("Maria Lopez", school, nsf=httpx.Response(200, json={"response": {}})))
    _score(monkeypatch)
    openalex._trip(datetime.now(UTC) + timedelta(hours=2))
    run_id, program_id, task_id = _setup(
        school, "Maria Lopez", field="regenerative biology", program_name="Molecular Biology"
    )
    model = BriefSaver()
    _research(monkeypatch, run_id, task_id, model)  # no OpenAlexBudgetExhausted

    assert "dblp.org" not in recorder.hosts()  # not a computing field
    brief = model.briefs[0]
    assert "nih:777" in brief and "Active grants" in brief and "NIH RePORTER" in brief
    prof, papers, candidate = _saved(program_id)
    assert prof.openalex_id is None
    assert papers[0].title == "Single-cell maps of tissue regeneration [NIH grant R01GM123456]"
    assert papers[0].abstract.startswith("We map regeneration")
    assert any(s["label"] == "NIH RePORTER" for s in prof.socials)
    assert "Verified via NIH RePORTER" in candidate.rationale


@pytest.mark.pipeline
def test_without_another_source_the_task_still_waits(monkeypatch, transport):
    school = _school_name()
    empty = httpx.Response(200, json={"results": [], "response": {}})
    transport(Recorder("Maria Lopez", school, nih=empty, nsf=empty))
    until = datetime.now(UTC) + timedelta(hours=2)
    openalex._trip(until)
    run_id, _program_id, task_id = _setup(
        school, "Maria Lopez", field="regenerative biology", program_name="Molecular Biology"
    )

    async def no_agent(*args, **kwargs):
        raise AssertionError("no model call while nothing can verify them")

    monkeypatch.setattr(prospect_tasks, "run_agent_task", no_agent)
    with pytest.raises(openalex.OpenAlexBudgetExhausted):
        _research(monkeypatch, run_id, task_id)


def test_switched_off_sources_are_never_called(monkeypatch, transport):
    monkeypatch.setattr(settings, "verification_sources", "faculty_page")
    school = _school_name()
    recorder = transport(Recorder("Jane Smith", school))
    _nobody_on_openalex(monkeypatch)
    run_id, program_id, _ = _setup(school, "Jane Smith")

    async def go():
        async with SessionLocal() as session:
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=await session.get(Run, run_id), program=program)
            return await HANDLERS["find_openalex_author"]({"name": "Jane Smith"}, ctx)

    assert asyncio.run(go()) == {"candidates": []}
    assert recorder.sent == []
    assert not sources.stands_in_for_openalex()


LISTING = """<html><head><title>People | Computer Science</title></head><body>
<h1>Our faculty</h1><p>Chair: Carol White</p>
<ul>
 <li class="card"><h3>Jane Smith</h3><p>Professor of Robotics</p>
  <a href="https://orcid.org/0000-0002-1825-0097">ORCID</a>
  <a href="https://dblp.org/pid/12/3456.html">DBLP</a>
  <a href="https://scholar.google.com/citations?user=AbCdEfGhIjKl&hl=en">Scholar</a></li>
 <li class="card"><h3>Bob Jones</h3><p>Associate Professor</p>
  <a href="https://orcid.org/0000-0001-5109-3700">ORCID</a>
  <a href="https://www.semanticscholar.org/author/Bob-Jones/1741101">S2</a></li>
</ul></body></html>"""


def test_profile_ids_are_read_next_to_each_name():
    profile_ids.remember(LISTING, "https://cs.gti.example.edu/people")
    pages = ["https://www.gti.example.edu/"]  # another host of the same site
    assert profile_ids.lookup("Prof. Jane Smith", pages) == {
        "orcid": "0000-0002-1825-0097",
        "dblp": "12/3456",
        "scholar": "AbCdEfGhIjKl",
    }
    assert profile_ids.lookup("Bob Jones", pages) == {
        "orcid": "0000-0001-5109-3700",
        "semantic_scholar": "1741101",
    }
    assert profile_ids.lookup("Carol White", pages) == {}
    assert profile_ids.lookup("Jane Smith", ["https://other.example.org/"]) == {}


def test_a_profile_page_link_belongs_to_its_subject():
    page = """<html><head><title>Jane Smith - GTI</title></head><body>
    <h1>Jane Smith</h1><p>Works with Bob Jones.</p>
    <a href="https://scholar.google.com/citations?user=AbCdEfGhIjKl">Scholar</a></body></html>"""
    profile_ids.remember(page, "https://www.gti.example.edu/~jsmith")
    assert profile_ids.lookup("Jane Smith", ["https://gti.example.edu"]) == {"scholar": "AbCdEfGhIjKl"}
    assert profile_ids.lookup("Bob Jones", ["https://gti.example.edu"]) == {}


@pytest.mark.pipeline
def test_a_faculty_page_orcid_skips_the_name_search(monkeypatch, transport):
    recorder = transport(Recorder("Jane Smith", "unused"))
    school = _school_name()
    run_id, program_id, _ = _setup(school, "Jane Smith")
    profile_ids.remember(LISTING, "https://cs.gti.example.edu/people")
    sent = []

    async def get_json(path, params, **_):
        sent.append(params)
        assert params["filter"] == "orcid:0000-0002-1825-0097"
        # OpenAlex places her elsewhere: the school's own link still wins.
        return {"results": [{"id": "https://openalex.org/A42", "display_name": "Jane Q. Smith",
                             "last_known_institutions": [{"id": "I9", "display_name": "Elsewhere Lab"}]}]}  # fmt: skip

    monkeypatch.setattr(openalex, "_get_json", get_json)

    async def go():
        async with SessionLocal() as session:
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=await session.get(Run, run_id), program=program)
            found = await HANDLERS["find_openalex_author"]({"name": "Jane Smith"}, ctx)
            return found, ctx

    found, ctx = asyncio.run(go())
    assert len(sent) == 1 and "search" not in sent[0]
    (candidate,) = found["candidates"]
    assert candidate["openalex_id"] == "https://openalex.org/A42"
    assert candidate["verified_by"] == "faculty_page" and candidate["source"] == "orcid"
    assert grounding.at_school(ctx.author_candidates["A42"], school)
    assert recorder.sent == []


def test_the_dblp_record_is_parsed():
    record = __import__("api.prospects.dblp", fromlist=["x"]).parse_person(
        dblp_person("Jane Smith", "GTI"), "12/3456"
    )
    assert record["name"] == "Jane Smith"
    assert record["orcid"] == "0000-0002-1825-0097"
    assert record["affiliations"] == ["GTI, Testville, USA"]
    assert [w["year"] for w in record["works"]] == [THIS_YEAR, THIS_YEAR - 1, 1999]
    from api.prospects import dblp

    assert len(dblp.recent_works(record)) == 2
    assert dblp.parse_person("not xml", "x") is None


def test_institution_matching_is_strict_without_ids():
    match = sources.institution_match
    assert match(["Massachusetts Institute of Technology, Cambridge, MA, USA"], ["MIT"])
    assert match(["UNIVERSITY OF MICHIGAN AT ANN ARBOR"], ["University of Michigan"])
    assert match(["UNIV OF NORTH CAROLINA CHAPEL HILL"], ["University of North Carolina at Chapel Hill"])
    assert match(["Carnegie-Mellon University"], ["Carnegie Mellon University"])
    assert not match(["Michigan State University, East Lansing"], ["University of Michigan"])
    assert not match(["Washington University in St. Louis"], ["University of Washington"])
    assert not match(["Georgia Institute of Technology"], ["University of Georgia"])
    assert not match(["Texas A&M University"], ["University of Texas"])
    assert not match([], ["University of Texas"])


def test_cs_and_us_detection():
    assert sources.is_computing("machine learning", None)
    assert sources.is_computing(None, "Electrical and Computer Engineering")
    assert sources.is_computing("Robotics")
    assert not sources.is_computing("molecular biology", "Chemistry")
    us = sources.us_school
    assert us(type("S", (), {"country": "USA"})()) and us(type("S", (), {"country": None})())
    assert not us(type("S", (), {"country": "Ghana"})())


def test_an_outage_is_skipped_and_not_retried_per_task(monkeypatch, transport):
    school = _school_name()
    recorder = transport(
        Recorder(
            "Jane Smith", school, dblp=httpx.Response(503), nih=httpx.Response(503),
            nsf=httpx.Response(503), orcid=httpx.Response(503),
        )
    )
    ctx = type("Ctx", (), {"run": type("R", (), {"field": "AI"})(), "program": type("P", (), {"name": "CS"})()})()
    school_row = type("S", (), {"name": school, "country": "USA"})()
    assert asyncio.run(sources.fallback_candidates(ctx, school_row, "Jane Smith")) == []
    assert len(recorder.sent) == 4
    assert asyncio.run(sources.fallback_candidates(ctx, school_row, "Jane Smith")) == []
    assert len(recorder.sent) == 4

    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    source_http.reset()
    transport(Recorder("Jane Smith", school, dblp=timeout, nih=timeout, nsf=timeout, orcid=timeout))
    assert asyncio.run(sources.fallback_candidates(ctx, school_row, "Jane Smith")) == []


def test_responses_are_cached_and_requests_paced(monkeypatch, transport):
    from api.prospects import dblp

    recorder = transport(Recorder("Jane Smith", "GTI"))
    first = asyncio.run(dblp.search_authors("Jane Smith"))
    again = asyncio.run(dblp.search_authors("Jane Smith"))
    assert first == again and len(first) == 2
    assert len(recorder.sent) == 1
    monkeypatch.setattr(settings, "source_min_interval_seconds", {"dblp": 100})
    monkeypatch.setattr(settings, "source_max_queue_seconds", 1)
    asyncio.run(dblp.search_authors("Bob Jones"))
    with pytest.raises(source_http.SourceUnavailable, match="busy"):
        asyncio.run(dblp.search_authors("Carol White"))


def test_nsf_awards_are_parsed(transport):
    from api.prospects import grants

    recorder = transport(Recorder("Maria Lopez", "GTI"))
    (award,) = asyncio.run(grants.nsf_awards("Maria", "Lopez"))
    assert recorder.sent[0].url.params["pdPIName"] == "Maria Lopez"
    assert award["pi_id"] == "maria-lopez@gti"
    assert award["work"]["title"] == "CAREER: Learning robots [NSF award 2112345]"
    assert award["work"]["active"] is True and award["work"]["year"] == THIS_YEAR - 1


def test_nih_request_and_grouping(transport):
    recorder = transport(Recorder("Maria Lopez", "Graduator Test Institute"))
    found = asyncio.run(sources._nih_lookup("Maria Lopez", ["Graduator Test Institute"]))
    body = json.loads(recorder.sent[0].content)
    assert body["criteria"]["pi_names"] == [{"first_name": "Maria", "last_name": "Lopez"}]
    (candidate,) = found  # the namesake at another university is left out
    assert candidate["openalex_id"] == "nih:777"
    assert candidate["active_grants"][0]["ends"] == FUTURE


def test_source_ids_survive_a_checkpoint():
    ctx = ToolContext(session=None, run=type("R", (), {"user_id": TEST_USER_ID})())  # type: ignore[arg-type]
    grounding.record_author_candidates(ctx, [{"openalex_id": "dblp:12/3456", "source": "dblp"}])
    grounding.record_works(ctx, "DBLP:12/3456", [{"title": "A paper"}])
    messages = grounding.attach_to_checkpoint(ctx, [{"role": "user", "content": "go"}])
    fresh = ToolContext(session=None, run=type("R", (), {"user_id": TEST_USER_ID})())  # type: ignore[arg-type]
    grounding.restore_from_checkpoint(fresh, json.loads(json.dumps(messages)))
    assert grounding.works_for(fresh, "dblp:12/3456") == [{"title": "A paper"}]
    assert grounding.author_key("https://openalex.org/a123") == "A123"


def orcid_search(name: str, school: str) -> dict:
    first, last = name.split()[0], name.split()[-1]
    return {
        "num-found": 2,
        "expanded-result": [
            {"orcid-id": "0000-0001-2345-6789", "given-names": first, "family-names": last,
             "other-name": [], "institution-name": [school, "Some Hospital"]},
            {"orcid-id": "0000-0009-8765-4321", "given-names": first, "family-names": last,
             "other-name": [], "institution-name": ["Elsewhere University"]},
        ],
    }  # fmt: skip


def orcid_works() -> dict:
    def group(title, year, doi=None):
        ids = [{"external-id-type": "doi", "external-id-value": doi}] if doi else []
        return {"external-ids": {"external-id": ids},
                "work-summary": [{"title": {"title": {"value": title}},
                                  "publication-date": {"year": {"value": str(year)}},
                                  "journal-title": {"value": "Cell"}, "url": None}]}  # fmt: skip

    return {
        "group": [
            group("Single-cell maps of tissue regeneration", THIS_YEAR, "10.1/REGEN"),
            group("Wound healing in zebrafish", THIS_YEAR - 1),
            group("An old paper", 1999),
        ]
    }


def _orcid_recorder(name: str, school: str, **overrides) -> Recorder:
    def orcid(request):
        if request.url.path.endswith("/works"):
            return httpx.Response(200, json=orcid_works())
        if request.url.path.endswith("/personal-details"):
            first, last = name.split()[0], name.split()[-1]
            return httpx.Response(200, json={"name": {"given-names": {"value": first}, "family-name": {"value": last}}})
        return httpx.Response(200, json=orcid_search(name, school))

    def s2(request):
        ids = json.loads(request.content)["ids"]
        assert ids == ["DOI:10.1/regen"]
        return httpx.Response(200, json=[{"externalIds": {"DOI": "10.1/REGEN"}, "abstract": "We map regeneration."}])

    return Recorder(name, school, orcid=orcid, semantic_scholar=s2, **overrides)


@pytest.mark.pipeline
def test_orcid_verifies_any_field_anywhere_while_openalex_waits(monkeypatch, transport):
    school = _school_name()
    recorder = transport(_orcid_recorder("Ama Mensah", school))
    _score(monkeypatch)
    openalex._trip(datetime.now(UTC) + timedelta(hours=2))
    run_id, program_id, task_id = _setup(
        school, "Ama Mensah", field="regenerative biology", program_name="Molecular Biology", country="Ghana"
    )
    model = BriefSaver()
    _research(monkeypatch, run_id, task_id, model)  # no OpenAlexBudgetExhausted

    assert "api.reporter.nih.gov" not in recorder.hosts()  # not a US school
    brief = model.briefs[0]
    assert "orcid:0000-0001-2345-6789" in brief and "ORCID" in brief
    prof, _papers, candidate = _saved(program_id)
    assert prof.openalex_id is None
    assert any(s["url"] == "https://orcid.org/0000-0001-2345-6789" for s in prof.socials)
    assert "Verified via their ORCID record" in candidate.rationale
    assert "1 abstracts and 1 titles" in candidate.rationale


def test_orcid_matches_the_school_strictly():
    school = "Kwame Nkrumah University of Science and Technology"
    assert sources.institution_match([school, "Some Hospital"], [school])
    assert not sources.institution_match(["University of Science and Technology"], [school])


def test_orcid_works_are_parsed():
    from api.prospects import orcid

    works = orcid.parse_works(orcid_works())
    assert [w["year"] for w in works] == [THIS_YEAR, THIS_YEAR - 1, 1999]
    assert works[0]["doi"] == "10.1/regen" and works[0]["url"] == "https://doi.org/10.1/regen"
    assert len(orcid.recent_works(works)) == 2


@pytest.mark.pipeline
def test_a_faculty_page_orcid_is_read_from_orcid_while_openalex_waits(monkeypatch, transport):
    recorder = transport(_orcid_recorder("Jane Smith", "unused"))
    school = _school_name()
    run_id, program_id, _ = _setup(school, "Jane Smith")
    profile_ids.remember(LISTING, "https://cs.gti.example.edu/people")
    openalex._trip(datetime.now(UTC) + timedelta(hours=2))

    async def go():
        async with SessionLocal() as session:
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=await session.get(Run, run_id), program=program)
            return await HANDLERS["find_openalex_author"]({"name": "Jane Smith"}, ctx)

    (candidate,) = asyncio.run(go())["candidates"]
    assert candidate["openalex_id"] == "orcid:0000-0002-1825-0097"
    assert candidate["verified_by"] == "faculty_page" and candidate["source"] == "orcid_record"
    assert "expanded-search" not in " ".join(str(r.url) for r in recorder.sent)
