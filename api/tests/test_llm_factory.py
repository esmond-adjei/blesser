import asyncio

import pytest

from api.agent.llm.anthropic_provider import AnthropicProvider
from api.agent.llm.base import to_anthropic_tools, to_openai_tools
from api.agent.llm.factory import (
    get_provider,
    get_provider_info,
)
from api.agent.llm.openai_compat_provider import OpenAICompatProvider
from api.agent.tools import TOOL_DEFINITIONS
from api.core.config import Settings


def _settings_for(provider: str, model: str = "claude-sonnet-4-6") -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        llm_provider=provider,
        llm_model=model,
        llm_api_key="test-key",
    )


@pytest.mark.parametrize(
    ("provider", "cls"),
    [
        ("anthropic", AnthropicProvider),
        ("openai", OpenAICompatProvider),
        ("ollama", OpenAICompatProvider),
        ("gemini", OpenAICompatProvider),
        ("openai-compatible", OpenAICompatProvider),
    ],
)
def test_factory_returns_the_providers_class(provider, cls):
    p = get_provider(_settings_for(provider))
    assert isinstance(p, cls)
    assert p.name == provider


def test_factory_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        get_provider(_settings_for("claude-unknown"))


def test_factory_applies_per_provider_default_model():
    # Still on the anthropic-era default -> provider default kicks in.
    assert getattr(get_provider(_settings_for("openai")), "model") == "gpt-4o-mini"
    assert getattr(get_provider(_settings_for("ollama")), "model") == "llama3.1"
    assert getattr(get_provider(_settings_for("gemini")), "model") == "gemini-2.0-flash"
    assert getattr(get_provider(_settings_for("openai", "gpt-4o")), "model") == "gpt-4o"


def test_ollama_and_gemini_base_urls():
    assert (
        getattr(get_provider(_settings_for("ollama")), "base_url")
        == "http://localhost:11434/v1"
    )
    gemini = get_provider(_settings_for("gemini"))
    assert (
        getattr(gemini, "base_url")
        == "https://generativelanguage.googleapis.com/v1beta/openai/"
    )


def _compat_provider_with(calls, sent):
    from types import SimpleNamespace

    from api.agent.llm.openai_compat_provider import OpenAICompatProvider

    async def _create(**kwargs):
        sent.append(kwargs)
        message = SimpleNamespace(content="thinking", tool_calls=calls)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    provider = OpenAICompatProvider(model="m", api_key="k")
    provider._client = SimpleNamespace(  # pyright: ignore[reportAttributeAccessIssue]
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )
    return provider


def _compat_call(extra):
    from types import SimpleNamespace

    call = SimpleNamespace(
        type="function",
        id="call-1",
        function=SimpleNamespace(name="search_web", arguments='{"query": "x"}'),
    )
    if extra is not None:
        call.extra_content = extra
    return call


def test_openai_compat_preserves_tool_call_extras():
    """Gemini thinking models' follow-up turn 400s without the tool call's signature."""
    sig = {"google": {"thought_signature": "sig-123"}}
    provider = _compat_provider_with([_compat_call(sig)], [])
    out = asyncio.run(
        provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            system="sys",
            tools=[
                {
                    "name": "search_web",
                    "description": "",
                    "parameters": {"type": "object"},
                }
            ],
        )
    )
    assert out.tool_calls[0].extra_content == sig


def test_openai_compat_replays_extras_verbatim():
    sig = {"google": {"thought_signature": "sig-123"}}
    provider = _compat_provider_with([], [])
    native = provider._to_native_messages(
        [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "thinking",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "search_web",
                        "arguments": {"query": "x"},
                        "extra_content": sig,
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "name": "search_web",
                "content": "{}",
            },
        ],
        "sys",
    )
    assert native[2]["tool_calls"][0]["extra_content"] == sig

    plain = provider._to_native_messages(
        [
            {
                "role": "assistant",
                "content": "t",
                "tool_calls": [{"id": "c", "name": "n", "arguments": {}}],
            }
        ],
        "",
    )
    assert "extra_content" not in plain[0]["tool_calls"][0]


def test_tool_call_extra_falls_back_to_model_dump():
    from api.agent.llm.openai_compat_provider import _tool_call_extra

    class DumpOnly:
        def model_dump(self):
            return {"extra_content": {"google": {"thought_signature": "s"}}}

    assert _tool_call_extra(DumpOnly()) == {"google": {"thought_signature": "s"}}

    from types import SimpleNamespace

    assert _tool_call_extra(SimpleNamespace(type="function")) == {}


def test_only_gemini_requires_tool_call_extras():
    from api.agent.llm.openai_compat_provider import OpenAICompatProvider

    assert OpenAICompatProvider(
        model="m", api_key="k", provider_label="gemini"
    ).requires_tool_call_extras is True
    assert OpenAICompatProvider(model="m", api_key="k").requires_tool_call_extras is False


def test_gemini_streams_and_keeps_thought_signatures():
    """Gemini's signature rides on a tool call's first delta and must reach the final ToolCall."""
    from types import SimpleNamespace

    from api.agent.llm.openai_compat_provider import OpenAICompatProvider

    sig = {"google": {"thought_signature": "sig-123"}}

    def _delta(content=None, tool_calls=None):
        return SimpleNamespace(
            usage=None,
            choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=tool_calls))],
        )

    def _tc(**kw):
        call = SimpleNamespace(
            index=0,
            id=kw.get("id"),
            function=SimpleNamespace(name=kw.get("name"), arguments=kw.get("arguments")),
        )
        if "extra" in kw:
            call.extra_content = kw["extra"]
        return call

    chunks = [
        _delta(content="Looking"),
        _delta(tool_calls=[_tc(id="c1", name="search_web", arguments='{"query":', extra=sig)]),
        _delta(tool_calls=[_tc(arguments=' "x"}')]),
    ]
    sent: list[dict] = []

    async def _stream():
        for c in chunks:
            yield c

    async def _create(**kwargs):
        sent.append(kwargs)
        return _stream()

    provider = OpenAICompatProvider(model="m", api_key="k", provider_label="gemini")
    provider._client = SimpleNamespace(  # pyright: ignore[reportAttributeAccessIssue]
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )

    async def _collect():
        return [e async for e in provider.chat_stream([{"role": "user", "content": "hi"}], "sys", [])]

    events = asyncio.run(_collect())
    assert sent[0]["stream"] is True
    assert [e["text"] for e in events if e["type"] == "token"] == ["Looking"]
    call = events[-1]["response"].tool_calls[0]
    assert call.arguments == {"query": "x"}
    assert call.extra_content == sig


def test_tool_definitions_are_provider_neutral():
    assert len(TOOL_DEFINITIONS) >= 8
    for t in TOOL_DEFINITIONS:
        assert "name" in t and "description" in t and "parameters" in t
        assert t["parameters"]["type"] == "object"


def test_converters_keep_each_tools_schema():
    pairs = zip(to_anthropic_tools(TOOL_DEFINITIONS), to_openai_tools(TOOL_DEFINITIONS), TOOL_DEFINITIONS, strict=True)
    for anthropic, openai, definition in pairs:
        assert anthropic["input_schema"] == definition["parameters"]
        assert openai["function"]["parameters"] == definition["parameters"]


def test_provider_info_is_safe_to_log():
    info = get_provider_info(_settings_for("ollama"))
    assert info["llm_provider"] == "ollama"
    assert "test-key" not in str(info)


def test_generic_key_reaches_every_provider():
    for provider in ("anthropic", "openai", "ollama", "gemini", "openai-compatible"):
        assert getattr(get_provider(_settings_for(provider)), "api_key") == "test-key"


def test_ollama_needs_no_key():
    s = Settings(_env_file=None, llm_provider="ollama", llm_api_key="")  # pyright: ignore[reportCallIssue]
    assert s.resolve_llm_api_key() == "ollama"
    blank = Settings(_env_file=None, llm_api_key="")  # pyright: ignore[reportCallIssue]
    assert blank.resolve_llm_api_key() == ""


def test_anthropic_message_conversion_groups_tool_results():
    p = AnthropicProvider(model="m", api_key="k")
    native = p._to_native_messages(
        [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "t1", "name": "search_web", "arguments": {"query": "x"}}
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "t1",
                "name": "search_web",
                "content": "{}",
            },
        ]
    )
    assert native[0]["role"] == "user"
    assert native[1]["role"] == "assistant"
    tool_uses = [b for b in native[1]["content"] if b.get("type") == "tool_use"]
    assert len(tool_uses) == 1 and tool_uses[0]["name"] == "search_web"
    assert native[2]["role"] == "user"
    assert native[2]["content"][0]["type"] == "tool_result"


def _user_text(message: dict) -> str:
    """The text of a user message, whatever shape it came in."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n\n".join(
        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
    )


def test_anthropic_merges_a_user_turn_into_the_tool_results():
    """Anthropic takes one user turn per message, so the student's words ride with the tool results."""
    p = AnthropicProvider(model="m", api_key="k")
    native = p._to_native_messages(
        [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "t1", "name": "search_web", "arguments": {"query": "x"}}
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "t1",
                "name": "search_web",
                "content": "{}",
            },
            {"role": "user", "content": "actually, focus on robotics"},
        ]
    )
    assert [m["role"] for m in native] == ["user", "assistant", "user"]
    blocks = native[2]["content"]
    assert blocks[0]["type"] == "tool_result"
    assert "actually, focus on robotics" in _user_text(native[2])


def test_anthropic_merges_two_user_turns_in_a_row():
    """Anthropic wants the roles to alternate."""
    p = AnthropicProvider(model="m", api_key="k")
    native = p._to_native_messages(
        [
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
        ]
    )
    assert [m["role"] for m in native] == ["user"]
    assert _user_text(native[0]) == "first\n\nsecond"


def test_openai_message_conversion_keeps_tool_call_ids():
    p = OpenAICompatProvider(model="m", api_key="k", provider_label="openai")
    native = p._to_native_messages(
        [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "t1", "name": "search_web", "arguments": {"query": "x"}}
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "t1",
                "name": "search_web",
                "content": "{}",
            },
        ],
        system="sys",
    )
    assert native[0] == {"role": "system", "content": "sys"}
    assert native[2]["tool_calls"][0]["id"] == "t1"
    assert native[3] == {"role": "tool", "tool_call_id": "t1", "content": "{}"}


def test_a_stream_that_stops_at_its_limit_is_marked_truncated():
    """A thinking model behind Ollama can reason until max_tokens and say nothing."""
    from types import SimpleNamespace

    from api.agent.llm.openai_compat_provider import OpenAICompatProvider

    def _run(finish):
        async def _stream():
            yield SimpleNamespace(
                usage=None,
                choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=None), finish_reason=finish)],
            )

        async def _create(**kwargs):
            return _stream()

        provider = OpenAICompatProvider(model="m", api_key="k")
        provider._client = SimpleNamespace(  # pyright: ignore[reportAttributeAccessIssue]
            chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
        )

        async def _done():
            async for event in provider.chat_stream([{"role": "user", "content": "hi"}], "sys", []):
                if event["type"] == "done":
                    return event["response"]

        return asyncio.run(_done())

    cut = _run("length")
    assert cut.truncated and cut.empty_at_limit
    assert not _run("stop").truncated


def test_a_thinking_models_reasoning_streams_apart_from_its_reply():
    """Ollama sends reasoning as `delta.reasoning` (vLLM as `reasoning_content`)."""
    from types import SimpleNamespace

    from api.agent.llm.openai_compat_provider import OpenAICompatProvider

    def _delta(**fields):
        base = {"content": None, "tool_calls": None}
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=SimpleNamespace(**{**base, **fields}), finish_reason=None)])

    async def _stream():
        yield _delta(reasoning="The user wants ")
        yield _delta(reasoning_content="a shorter summary.")
        yield _delta(content="Here it is.")

    async def _create(**kwargs):
        return _stream()

    provider = OpenAICompatProvider(model="m", api_key="k")
    provider._client = SimpleNamespace(  # pyright: ignore[reportAttributeAccessIssue]
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )

    async def _events():
        return [e async for e in provider.chat_stream([{"role": "user", "content": "hi"}], "sys", [])]

    events = asyncio.run(_events())
    assert [e["text"] for e in events if e["type"] == "reasoning"] == ["The user wants ", "a shorter summary."]
    assert [e["text"] for e in events if e["type"] == "token"] == ["Here it is."]
    done = events[-1]["response"]
    assert done.text == "Here it is." and done.reasoning == "The user wants a shorter summary."
