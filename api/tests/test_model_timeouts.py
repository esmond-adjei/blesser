import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from api.agent.llm.base import LLMResponse, ToolCall, is_transient
from api.core.config import settings
from api.core.db import SessionLocal
from api.prospects import grounding
from api.runs import queue
from api.runs.models import ResearchTask, Run, TaskStatus
from tests.conftest import TEST_USER_ID


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(settings, "llm_retry_backoff_seconds", 0)


def _ctx(**extra):
    return SimpleNamespace(session=None, user_id=None, run=None, **extra)


def _history(turns: int) -> list[dict]:
    """A resumable history with one tool result per turn."""
    out: list[dict] = [{"role": "user", "content": "go"}]
    for t in range(1, turns + 1):
        out.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": f"c{t}", "name": "fetch_page", "arguments": {}}],
            }
        )
        out.append(
            {
                "role": "tool",
                "tool_call_id": f"c{t}",
                "name": "fetch_page",
                "content": "page text " * 50,
                "_turn": t,
            }
        )
    return out


def test_transient_classification():
    class APITimeoutError(Exception):
        pass

    class Upstream(Exception):
        status_code = 503

    class BadRequest(Exception):
        status_code = 400

    assert is_transient(httpx.ReadTimeout("slow"))
    assert is_transient(APITimeoutError())
    assert is_transient(Upstream())
    assert not is_transient(BadRequest())
    assert not is_transient(ValueError("bug"))


def test_timeout_retries_the_turn(monkeypatch):
    import api.agent.orchestrator as orch

    seen: list[list[dict]] = []

    class SlowThenFine:
        async def chat(self, messages, system, tools, max_tokens=4096):
            seen.append(messages)
            if len(seen) == 1:
                raise httpx.ReadTimeout("the model took too long")
            return LLMResponse(text="finished", tool_calls=[])

    monkeypatch.setattr(orch, "get_provider", lambda **_: SlowThenFine())
    out = asyncio.run(
        orch.run_agent_task("sys", "go", ctx=_ctx(), resume_messages=_history(4))
    )
    assert out["final_text"] == "finished"
    assert out["turns"] == 5
    assert len(seen) == 2
    assert seen[1] == seen[0]
    assert "omitted" not in seen[1][-1]["content"]


def test_non_transient_error_is_not_retried(monkeypatch):
    import api.agent.orchestrator as orch

    calls = {"n": 0}

    class Broken:
        async def chat(self, messages, system, tools, max_tokens=4096):
            calls["n"] += 1
            raise ValueError("bad request")

    monkeypatch.setattr(orch, "get_provider", lambda **_: Broken())
    with pytest.raises(ValueError):
        asyncio.run(orch.run_agent_task("sys", "go", ctx=_ctx()))
    assert calls["n"] == 1


def test_persistent_timeout_raises_after_bounded_retries(monkeypatch):
    import api.agent.orchestrator as orch

    calls = {"n": 0}

    class AlwaysSlow:
        async def chat(self, messages, system, tools, max_tokens=4096):
            calls["n"] += 1
            raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(orch, "get_provider", lambda **_: AlwaysSlow())
    monkeypatch.setattr(settings, "llm_turn_retries", 2)
    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(orch.run_agent_task("sys", "go", ctx=_ctx()))
    assert calls["n"] == 3


def _seed_task(checkpoint: list[dict] | None = None) -> str:
    async def go():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID,
                region="U",
                field="f",
                degree_level="phd",
                interest_statement="x",
                status="running",
            )
            session.add(run)
            await session.flush()
            task = ResearchTask(
                user_id=TEST_USER_ID, run_id=run.id, task_type="discover_programs"
            )
            if checkpoint is not None:
                task.messages_json = json.dumps(checkpoint)
            session.add(task)
            await session.commit()
            return task.id

    return asyncio.run(go())


def _process(monkeypatch, task_id: str, handler) -> ResearchTask:
    monkeypatch.setitem(queue.TASK_HANDLERS, "discover_programs", handler)

    async def fake_claim(session):
        task = await session.get(ResearchTask, task_id)
        task.status = TaskStatus.running
        task.attempt = (task.attempt or 0) + 1
        await session.commit()
        return task

    monkeypatch.setattr(queue, "_claim_next_task", fake_claim)
    assert asyncio.run(queue.process_one()) is True

    async def fetch():
        async with SessionLocal() as session:
            return await session.get(ResearchTask, task_id)

    return asyncio.run(fetch())


def test_transient_failure_requeues_with_checkpoint_until_the_cap(monkeypatch):
    from api.agent.orchestrator import add_task_usage

    monkeypatch.setattr(settings, "max_task_attempts", 3)
    checkpoint = _history(2)
    task_id = _seed_task(checkpoint)
    resumed_with = []

    async def slow_handler(
        session, task, run, on_event=None, resume_messages=None, on_checkpoint=None
    ):
        resumed_with.append(resume_messages)
        add_task_usage({"input_tokens": 5, "output_tokens": 1}, 7)
        raise httpx.ReadTimeout("the upstream service could not be reached")

    for attempt in (1, 2):
        task = _process(monkeypatch, task_id, slow_handler)
        assert task.status == TaskStatus.pending, attempt
        assert "Retrying" in (task.error or "")
        assert task.claimed_by is None
        assert task.messages_json is not None  # resumes from the checkpoint
        assert task.turns == 7  # not 0: the turns this attempt reached

    task = _process(monkeypatch, task_id, slow_handler)
    assert task.status == TaskStatus.error
    assert task.attempt == 3
    assert task.input_tokens == 15  # every attempt's spend is kept
    assert all(r == checkpoint for r in resumed_with)


def test_non_transient_failure_errors_at_once_with_turns(monkeypatch):
    from api.agent.orchestrator import add_task_usage

    task_id = _seed_task()

    async def bad_handler(
        session, task, run, on_event=None, resume_messages=None, on_checkpoint=None
    ):
        add_task_usage(None, 4)
        raise ValueError("boom")

    task = _process(monkeypatch, task_id, bad_handler)
    assert task.status == TaskStatus.error
    assert task.turns == 4


AUTHOR = {"openalex_id": "A1", "name": "Lee", "institution": "MIT"}
WORK = {"title": "Learning agile locomotion", "abstract": "Legged robots."}


def test_grounding_survives_resume(monkeypatch):
    import api.agent.orchestrator as orch

    class OneToolThenTimeout:
        def __init__(self):
            self.n = 0

        async def chat(self, messages, system, tools, max_tokens=4096):
            self.n += 1
            if self.n == 1:
                return LLMResponse(
                    text="",
                    tool_calls=[ToolCall(id="t1", name="get_author_works")],
                )
            raise ValueError("crash after the fetch")

    async def recording_dispatch(calls, ctx, task_type=None):
        grounding.record_author_candidates(ctx, [AUTHOR])
        grounding.record_works(ctx, "A1", [WORK])
        grounding.record_score(ctx, [WORK["abstract"]], {"score": 0.8})
        return [{"ok": True} for _ in calls]

    monkeypatch.setattr(orch, "get_provider", lambda **_: OneToolThenTimeout())
    monkeypatch.setattr(orch, "dispatch_batch", recording_dispatch)
    checkpoints = []

    async def on_checkpoint(messages):
        checkpoints.append(json.loads(json.dumps(messages)))

    with pytest.raises(ValueError):
        asyncio.run(
            orch.run_agent_task("sys", "go", ctx=_ctx(), on_checkpoint=on_checkpoint)
        )
    assert grounding.CHECKPOINT_KEY in checkpoints[-1][-1]

    # A fresh attempt with a fresh context: the save grounds without refetching.
    sent = []

    class Finishes:
        async def chat(self, messages, system, tools, max_tokens=4096):
            sent.append(messages)
            return LLMResponse(text="finished", tool_calls=[])

    monkeypatch.setattr(orch, "get_provider", lambda **_: Finishes())
    resumed = _ctx()
    asyncio.run(
        orch.run_agent_task("sys", "go", ctx=resumed, resume_messages=checkpoints[-1])
    )
    assert all(grounding.CHECKPOINT_KEY not in m for m in sent[0])
    error, grounded = grounding.ground_professor_save(
        {
            "openalex_id": "A1",
            "papers": [{"title": WORK["title"]}],
            "similarity_score": 0.8,
        },
        resumed,
        "MIT",
    )
    assert error is None
    assert grounded["similarity_score"] == 0.8


def test_empty_abstracts_are_refused_with_what_to_send(monkeypatch):
    from api.candidates import scoring
    from api.candidates import tools as candidate_tools

    async def never(*_a, **_k):  # pragma: no cover - must not be called
        raise AssertionError("scored nothing")

    monkeypatch.setattr(scoring, "score_interest_for_ctx_async", never)
    out = asyncio.run(
        candidate_tools.handle_score_alignment(
            {"interest_text": "robots", "abstracts": ["", "  "]},
            SimpleNamespace(user_id=TEST_USER_ID),
        )
    )
    assert "title" in out["error"]


class _Tracked:
    """A provider that records how many of its calls overlap."""

    def __init__(self, name: str, seconds: float = 0.02):
        self.name = name
        self.base_url = "http://gpu-box:11434/v1"
        self.seconds = seconds
        self.live = 0
        self.peak = 0

    async def chat(self, messages, system, tools, max_tokens=4096):
        self.live += 1
        self.peak = max(self.peak, self.live)
        try:
            await asyncio.sleep(self.seconds)
        finally:
            self.live -= 1
        return LLMResponse(text="ok")


def _turns(provider, n: int):
    from api.agent.orchestrator import _chat_with_retry

    async def go():
        return await asyncio.gather(
            *(_chat_with_retry(provider, [], "sys", [], t) for t in range(n))
        )

    return asyncio.run(go())


def test_ollama_calls_are_capped_per_backend(monkeypatch):
    monkeypatch.setattr(settings, "ollama_max_concurrency", 2)
    monkeypatch.setattr(settings, "llm_max_concurrency", 0)
    provider = _Tracked("ollama")
    assert all(r.text == "ok" for r in _turns(provider, 8))
    assert provider.peak == 2


def test_hosted_calls_are_uncapped_by_default(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_concurrency", 0)
    provider = _Tracked("anthropic")
    _turns(provider, 8)
    assert provider.peak == 8


def test_waiting_for_a_slot_does_not_use_up_the_deadline(monkeypatch):
    # Four 60ms calls through one slot take 240ms in all, past the 150ms
    # deadline, yet none of them times out: each call's clock starts when
    # it gets the slot.
    monkeypatch.setattr(settings, "ollama_max_concurrency", 1)
    monkeypatch.setattr(settings, "llm_call_deadline_seconds", 0.15)
    monkeypatch.setattr(settings, "llm_turn_retries", 0)
    provider = _Tracked("ollama", seconds=0.06)
    assert all(r.text == "ok" for r in _turns(provider, 4))
    assert provider.peak == 1


def test_deadline_timeout_says_what_happened(monkeypatch):
    from api.core.egress import public_error

    monkeypatch.setattr(settings, "llm_call_deadline_seconds", 0.01)
    monkeypatch.setattr(settings, "llm_turn_retries", 0)
    with pytest.raises(TimeoutError) as caught:
        _turns(_Tracked("anthropic", seconds=1), 1)
    assert "no model reply within" in str(caught.value)
    assert public_error(TimeoutError()) == "TimeoutError"
