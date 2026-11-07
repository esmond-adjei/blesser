import asyncio
import types

import pytest

import api.agent.orchestrator as orch
from api.agent.llm.base import LLMResponse
from api.core.config import settings
from api.providers import service as providers_service


class _Done:
    async def chat(self, messages, system, tools, max_tokens=4096):
        return LLMResponse(text="done", tool_calls=[])


def _built_with(monkeypatch, *, small_model, resolved, setting="qwen3:8b"):
    built = []

    def get_provider(**kwargs):
        built.append(kwargs)
        return _Done()

    async def resolve(*args, **kwargs):
        return dict(resolved)

    monkeypatch.setattr(orch, "get_provider", get_provider)
    monkeypatch.setattr(providers_service, "resolve_llm_kwargs", resolve)
    monkeypatch.setattr(settings, "llm_small_model", setting)
    asyncio.run(orch.run_agent_task("sys", "go", ctx=types.SimpleNamespace(), small_model=small_model))  # type: ignore[arg-type]
    return built[0]


def test_a_small_call_on_the_system_model_uses_the_small_model(monkeypatch):
    assert _built_with(monkeypatch, small_model=True, resolved={}) == {"model": "qwen3:8b"}


@pytest.mark.parametrize(
    ("small_model", "resolved", "setting"),
    [
        (False, {}, "qwen3:8b"),  # the full loop keeps LLM_MODEL
        (True, {}, ""),  # no small model configured
        (True, {"provider": "openai", "model": "gpt-x", "api_key": "k"}, "qwen3:8b"),  # their own model
    ],
)
def test_everything_else_keeps_its_model(monkeypatch, small_model, resolved, setting):
    assert _built_with(monkeypatch, small_model=small_model, resolved=resolved, setting=setting) == resolved
