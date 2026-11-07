import asyncio


def _scripted_stub(script, seen):
    """Each entry: ("call", tool, args) or ("final", text)."""
    from api.agent.llm.base import LLMResponse, ToolCall

    calls = {"n": 0}

    class StubProvider:
        async def chat(self, messages, system, tools, max_tokens=4096):
            seen.append(messages)
            kind = script[calls["n"]]
            calls["n"] += 1
            if kind[0] == "final":
                return LLMResponse(text=kind[1], tool_calls=[])
            return LLMResponse(
                text="",
                tool_calls=[
                    ToolCall(id=f"t{calls['n']}", name=kind[1], arguments=kind[2])
                ],
            )

    return StubProvider()


def test_dispatch_exception_becomes_tool_error(monkeypatch):
    import api.agent.orchestrator as orch

    seen = []
    stub = _scripted_stub(
        [
            ("call", "fetch_page", {"url": "https://www.ox.ac.uk/page"}),
            ("call", "save_program", {"school_name": "Oxford"}),
            ("final", "saved one despite the 403"),
        ],
        seen,
    )
    monkeypatch.setattr(orch, "get_provider", lambda: stub)

    calls = []

    # dispatch_batch is the seam: it takes [(name, arguments)] and returns results in request order.
    async def flaky_dispatch(batch, ctx, task_type=None):
        out = []
        for name, _args in batch:
            calls.append(name)
            if name == "fetch_page":
                out.append(
                    {
                        "error": "fetch_page failed: Client error '403 Forbidden' "
                        "for url 'https://www.ox.ac.uk/page'"
                    }
                )
            else:
                out.append({"program_id": "p1"})
        return out

    monkeypatch.setattr(orch, "dispatch_batch", flaky_dispatch)

    out = asyncio.run(orch.run_agent_task("sys", "go", ctx=object()))  # type: ignore[arg-type]
    assert out["final_text"] == "saved one despite the 403"
    assert calls == ["fetch_page", "save_program"]
    assert out["tool_log"][0]["tool"] == "fetch_page"
    assert "error" in out["tool_log"][0]["result"]
    assert "403" in out["tool_log"][0]["result"]["error"]


def _fake_client(response=None, exc=None):
    """Stand-in for web.py's cached AsyncClient; web.fetch_client rebuilds it when `is_closed` is True."""

    from contextlib import asynccontextmanager

    class FakeClient:
        is_closed = False

        async def get(self, url):
            if exc is not None:
                raise exc
            return response

        @asynccontextmanager
        async def stream(self, method, url, **kwargs):
            # egress.safe_get streams every hop.
            yield await self.get(url)

        async def aclose(self):
            pass

    return FakeClient()


def _public_dns(monkeypatch):
    from api.core import egress

    async def resolve(host, port):
        return ["93.184.216.34"]

    monkeypatch.setattr(egress, "_resolve", resolve)


def test_fetch_page_403_returns_guidance(monkeypatch):
    import httpx as real_httpx

    from api.prospects import web

    _public_dns(monkeypatch)
    req = real_httpx.Request("GET", "https://www.ox.ac.uk/dept")
    monkeypatch.setattr(
        web,
        "_fetch_client",
        _fake_client(response=real_httpx.Response(403, request=req)),
    )
    out = asyncio.run(web.fetch_page("https://www.ox.ac.uk/dept"))
    assert isinstance(out, str)
    assert "403" in out
    assert "different source" in out


def test_fetch_page_connection_error_returns_guidance(monkeypatch):
    import httpx as real_httpx

    from api.prospects import web

    _public_dns(monkeypatch)
    monkeypatch.setattr(
        web, "_fetch_client", _fake_client(exc=real_httpx.ConnectError("unreachable"))
    )
    out = asyncio.run(web.fetch_page("https://example.edu/dept"))
    assert isinstance(out, str)
    assert "different source" in out
