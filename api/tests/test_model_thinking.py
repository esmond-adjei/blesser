import asyncio
from types import SimpleNamespace as NS

import anthropic
import httpx

from api.agent.llm.anthropic_provider import AnthropicProvider, _thinking_config
from api.agent.llm.base import ANTHROPIC_THINKING, foreign_extras
from api.agent.llm.openai_compat_provider import OpenAICompatProvider, split_thinking


def _collect(gen):
    async def run():
        return [e async for e in gen]

    return asyncio.run(run())


def test_claude_models_that_think_are_asked_for_readable_thoughts():
    assert _thinking_config("claude-opus-5-5") == {"type": "adaptive", "display": "summarized"}
    assert _thinking_config("claude-sonnet-4-6") == {"type": "adaptive"}
    assert _thinking_config("claude-haiku-5-5") == {"type": "adaptive", "display": "summarized"}
    # Older models keep their old requests.
    assert _thinking_config("claude-haiku-4-5") is None
    assert _thinking_config("claude-sonnet-4-5-20250929") is None
    assert _thinking_config("claude-3-5-sonnet-20241022") is None


class _Stream:
    def __init__(self, events):
        self.events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def gen():
            for e in self.events:
                yield e

        return gen()


def _claude(events_per_call):
    """Streams the given events call by call (an exception raises); records each request."""
    provider = AnthropicProvider(model="claude-opus-5-5", api_key="k")
    calls = list(events_per_call)
    requests: list[dict] = []

    def stream(**kwargs):
        requests.append(kwargs)
        step = calls.pop(0)
        if isinstance(step, Exception):
            raise step
        return _Stream(step)

    provider._client = NS(messages=NS(stream=stream))  # pyright: ignore[reportAttributeAccessIssue]
    return provider, requests


_TURN = [
    NS(type="content_block_start", index=0, content_block=NS(type="thinking")),
    NS(type="content_block_delta", index=0, delta=NS(type="thinking_delta", thinking="Read it first.")),
    NS(type="content_block_delta", index=0, delta=NS(type="signature_delta", signature="sig")),
    NS(type="content_block_start", index=1, content_block=NS(type="tool_use", id="t1", name="read_document")),
    NS(type="content_block_delta", index=1, delta=NS(type="input_json_delta", partial_json="{}")),
    NS(type="message_delta", usage=NS(output_tokens=9), delta=NS(stop_reason="tool_use")),
]


def test_claude_thoughts_stream_and_their_blocks_stay_with_the_tool_call():
    provider, requests = _claude([_TURN])
    events = _collect(provider.chat_stream([{"role": "user", "content": "hi"}], "sys", []))
    assert requests[0]["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert [e["text"] for e in events if e["type"] == "reasoning"] == ["Read it first."]
    response = events[-1]["response"]
    assert response.reasoning == "Read it first."
    assert response.tool_calls[0].extra_content[ANTHROPIC_THINKING] == [
        {"type": "thinking", "thinking": "Read it first.", "signature": "sig"}
    ]


def _call(id_, thought):
    return {"id": id_, "name": "read_document", "arguments": {},
            "extra_content": {ANTHROPIC_THINKING: [{"type": "thinking", "thinking": thought, "signature": "s"}]}}


HISTORY = [
    {"role": "user", "content": "first"},
    {"role": "assistant", "content": "", "tool_calls": [_call("a", "old")]},
    {"role": "tool", "tool_call_id": "a", "content": "doc"},
    {"role": "assistant", "content": "Done."},
    {"role": "user", "content": "second"},
    {"role": "assistant", "content": "Looking.", "tool_calls": [_call("b", "new")]},
    {"role": "tool", "tool_call_id": "b", "content": "doc"},
]


def test_only_the_tool_loop_under_way_sends_its_thinking_back():
    native = AnthropicProvider(model="claude-opus-5-5", api_key="k")._to_native_messages(HISTORY)
    assistant = [m["content"] for m in native if m["role"] == "assistant"]
    types = [[b["type"] for b in c] if isinstance(c, list) else c for c in assistant]
    assert types == [["tool_use"], ["text"], ["thinking", "text", "tool_use"]]
    assert assistant[2][0]["thinking"] == "new"


def test_refused_thinking_is_dropped_and_the_request_sent_again():
    refused = anthropic.BadRequestError(
        "messages.5.content.0: Invalid `signature` in `thinking` block.",
        response=httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com")),
        body=None,
    )
    provider, requests = _claude([refused, _TURN, _TURN])
    events = _collect(provider.chat_stream(HISTORY, "sys", []))
    assert events[-1]["type"] == "done"
    assert "thinking" not in str(requests[1]["messages"])
    _collect(provider.chat_stream(HISTORY, "sys", []))
    assert len(requests) == 3 and "'thinking'" not in str(requests[2]["messages"])


def test_claude_thinking_is_never_sent_to_another_provider():
    extra = {ANTHROPIC_THINKING: [{"type": "thinking"}], "google": {"thought_signature": "x"}}
    assert foreign_extras(extra, "gemini") == {"google": {"thought_signature": "x"}}
    assert foreign_extras(extra, "anthropic") == extra


def _compat(chunks, label="ollama", model="m"):
    requests: list[dict] = []

    async def create(**kwargs):
        requests.append(kwargs)

        async def stream():
            for content in chunks:
                yield NS(usage=None, choices=[NS(delta=NS(content=content, tool_calls=None), finish_reason=None)])

        return stream()

    provider = OpenAICompatProvider(model=model, api_key="k", provider_label=label)
    provider._client = NS(chat=NS(completions=NS(create=create)))  # pyright: ignore[reportAttributeAccessIssue]
    return provider, requests


def test_reasoning_written_in_think_tags_streams_as_thoughts():
    provider, _ = _compat(["<th", "ink>Check the", " dates.</thi", "nk>\n\nAll", " good."])
    events = _collect(provider.chat_stream([{"role": "user", "content": "hi"}], "sys", []))
    assert "".join(e["text"] for e in events if e["type"] == "reasoning") == "Check the dates."
    assert "".join(e["text"] for e in events if e["type"] == "token") == "All good."
    assert events[-1]["response"].text == "All good."


def test_a_reply_that_merely_starts_with_markup_is_left_alone():
    assert split_thinking("<b>Bold</b> start") == ("", "<b>Bold</b> start")
    assert split_thinking("<thought>Plan.</thought>Answer") == ("Plan.", "Answer")
    # Cut off mid-thought: nothing said yet, so Gradis asks again with room.
    assert split_thinking("<think>Still going") == ("Still going", "")


def test_gemini_is_asked_for_its_thoughts_when_it_has_them():
    google = {"extra_body": {"google": {"thinking_config": {"include_thoughts": True}}}}
    for model, asked in [("gemini-2.5-flash", True), ("gemini-3-pro", True), ("gemini-2.0-flash", False)]:
        provider, requests = _compat(["Hi"], label="gemini", model=model)
        _collect(provider.chat_stream([{"role": "user", "content": "hi"}], "sys", []))
        assert (requests[0].get("extra_body") == google) is asked, model
    provider, requests = _compat(["Hi"], label="openai", model="gpt-5")
    _collect(provider.chat_stream([{"role": "user", "content": "hi"}], "sys", []))
    assert "extra_body" not in requests[0]
