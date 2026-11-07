import asyncio
import json
from types import SimpleNamespace

from api.agent.llm.anthropic_provider import AnthropicProvider
from api.agent.llm.openai_compat_provider import _usage as openai_usage
from api.agent.orchestrator import ModelAllowanceRefused, add_task_usage
from api.core.config import settings
from api.core.db import SessionLocal
from api.metering.service import billable_input_tokens
from api.runs.models import ResearchTask, Run, TaskStatus
from api.runs.service import resume_run
from tests.conftest import TEST_USER_ID
from tests.test_model_timeouts import _history, _process, _seed_task

TOOLS = [
    {"name": "a", "description": "A", "parameters": {"type": "object"}},
    {"name": "b", "description": "B", "parameters": {"type": "object"}},
]


class _Messages:
    def __init__(self):
        self.kwargs: dict = {}

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            usage=SimpleNamespace(
                input_tokens=200,
                output_tokens=10,
                cache_read_input_tokens=1800,
                cache_creation_input_tokens=0,
            ),
        )


def _provider() -> tuple[AnthropicProvider, _Messages]:
    provider = AnthropicProvider(model="m", api_key="k")
    messages = _Messages()
    provider._client = SimpleNamespace(messages=messages)
    return provider, messages


def test_tools_and_system_carry_a_cache_breakpoint():
    provider, messages = _provider()
    response = asyncio.run(
        provider.chat([{"role": "user", "content": "go"}], "SYSTEM", TOOLS)
    )
    sent = messages.kwargs
    assert sent["system"] == [
        {"type": "text", "text": "SYSTEM", "cache_control": {"type": "ephemeral"}}
    ]
    assert "cache_control" not in sent["tools"][0]
    assert sent["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert response.usage == {
        "input_tokens": 2000,
        "cache_read_tokens": 1800,
        "output_tokens": 10,
    }


def test_prompt_cache_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "llm_prompt_cache", False)
    provider, messages = _provider()
    asyncio.run(provider.chat([{"role": "user", "content": "go"}], "SYSTEM", TOOLS))
    assert messages.kwargs["system"] == "SYSTEM"
    assert all("cache_control" not in t for t in messages.kwargs["tools"])


def test_openai_cached_tokens_are_reported():
    usage = SimpleNamespace(
        prompt_tokens=3000, prompt_tokens_details=SimpleNamespace(cached_tokens=2048)
    )
    assert openai_usage(usage) == {"input_tokens": 3000, "cache_read_tokens": 2048}
    assert openai_usage(SimpleNamespace(prompt_tokens=10)) == {"input_tokens": 10}


def test_cached_reads_count_at_their_price():
    assert billable_input_tokens({"input_tokens": 2000}) == 2000
    # 200 fresh + 1800 cached at a tenth.
    assert billable_input_tokens({"input_tokens": 2000, "cache_read_tokens": 1800}) == 380
    # A cache write costs a quarter more.
    assert billable_input_tokens({"input_tokens": 1000, "cache_write_tokens": 800}) == 1200


def test_refused_task_is_paused_with_the_run_and_resumes(monkeypatch):
    checkpoint = _history(2)
    task_id = _seed_task(checkpoint)

    async def refused(session, task, run, on_event=None, resume_messages=None, on_checkpoint=None):
        add_task_usage({"input_tokens": 40, "output_tokens": 4}, 3)
        raise ModelAllowanceRefused(
            "You've used today's 1,000,000-token allowance on the shared model."
        )

    task = _process(monkeypatch, task_id, refused)
    assert task.status == TaskStatus.paused
    assert task.error.startswith("Paused: You've used today's")
    assert task.claimed_by is None
    assert json.loads(task.messages_json) == checkpoint
    assert task.input_tokens == 40

    async def after():
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            run = await session.get(Run, task.run_id)
            before = run.status
            manual = ResearchTask(
                user_id=TEST_USER_ID,
                run_id=run.id,
                task_type="discover_programs",
                status=TaskStatus.paused,
            )
            session.add(manual)
            await session.commit()
            await resume_run(session, TEST_USER_ID, run.id)
            await session.refresh(task)
            await session.refresh(manual)
            await session.refresh(run)
            return before, run.status, task.status, task.error, manual.status

    before, after_status, task_status, error, manual_status = asyncio.run(after())
    assert before == "paused"
    assert after_status == "running"
    assert task_status == TaskStatus.pending
    assert error is None
    assert manual_status == TaskStatus.paused
