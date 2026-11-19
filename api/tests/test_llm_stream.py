import asyncio
from types import SimpleNamespace as NS

from api.agent.llm.openai_compat_provider import OpenAICompatProvider


def _chunk(content=None, tool_calls=None, finish=None, reasoning=None):
    delta = NS(content=content, tool_calls=tool_calls, reasoning=reasoning)
    return NS(choices=[NS(delta=delta, finish_reason=finish)], usage=None)


def _call(index, id=None, name=None, arguments=None):
    return NS(index=index, id=id, function=NS(name=name, arguments=arguments), extra_content=None)


def test_openai_stream_yields_text_and_assembles_tool_calls():
    chunks = [
        _chunk("<think>weigh it</think>"),
        _chunk("Let me "),
        _chunk("check."),
        _chunk(tool_calls=[_call(0, "c1", "search_catalog", '{"que')]),
        _chunk(tool_calls=[_call(0, arguments='ry": "seed"}')]),
        _chunk(finish="tool_calls"),
        NS(choices=[], usage=NS(prompt_tokens=10, completion_tokens=4, prompt_tokens_details=None)),
    ]

    async def stream():
        for chunk in chunks:
            yield chunk

    async def create(**kwargs):
        assert kwargs["stream"] is True
        return stream()

    provider = OpenAICompatProvider(model="m", api_key="k")
    provider._client = NS(chat=NS(completions=NS(create=create)))

    async def run():
        return [piece async for piece in provider.stream(messages=[{"role": "user", "content": "hi"}], system="s", tools=[])]

    pieces = asyncio.run(run())
    assert [p for k, p in pieces if k == "text"] == ["Let me ", "check."]
    kind, response = pieces[-1]
    assert kind == "done"
    assert response.text == "Let me check."
    assert response.reasoning == "weigh it"
    assert [(c.id, c.name, c.arguments) for c in response.tool_calls] == [("c1", "search_catalog", {"query": "seed"})]
    assert response.usage["output_tokens"] == 4
