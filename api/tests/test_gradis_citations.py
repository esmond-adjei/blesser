from api.agent.llm.base import ToolCall
from api.assistant import sources as gradis_sources
from api.assistant import tools as assistant_tools
from tests.test_assistant import ScriptProvider, _client, _transcript, _turn


def test_search_web_results_become_web_sources():
    out = gradis_sources.extract_sources(
        "search_web",
        {
            "results": [
                {"title": "Soft Robotics Lab", "url": "https://www.lab.example.edu/", "snippet": "We build  soft robots."},
                {"title": "No link", "url": ""},
            ]
        },
    )
    assert out == [
        {
            "kind": "web",
            "url": "https://www.lab.example.edu/",
            "title": "Soft Robotics Lab",
            "subtitle": "lab.example.edu",
            "snippet": "We build soft robots.",
        }
    ]


def test_fetch_page_cites_the_url_it_read():
    [page] = gradis_sources.extract_sources(
        "fetch_page",
        {"text": "Admissions\nApply by December 1.\nGRE optional."},
        {"url": "https://grad.example.edu/apply"},
    )
    assert page["kind"] == "web" and page["url"] == "https://grad.example.edu/apply"
    assert page["title"] == "Admissions"
    assert "December 1" in page["snippet"]
    assert gradis_sources.extract_sources(
        "fetch_page", {"text": "[Could not fetch https://x.example]"}, {"url": "https://x.example"}
    ) == []


def test_openalex_works_and_authors():
    [paper] = gradis_sources.extract_sources(
        "get_author_works",
        {"works": [{"title": "Grasping", "abstract": "We grasp.", "year": 2024, "venue": "ICRA", "url": "https://doi.org/1"}]},
    )
    assert paper == {
        "kind": "paper",
        "title": "Grasping",
        "url": "https://doi.org/1",
        "venue": "ICRA",
        "year": 2024,
        "snippet": "We grasp.",
    }
    [author] = gradis_sources.extract_sources(
        "find_openalex_author",
        {"candidates": [{"openalex_id": "https://openalex.org/A123", "display_name": "Ada Lovelace", "institution": "MIT", "works_count": 40}]},
    )
    assert author["kind"] == "author" and author["url"] == "https://openalex.org/A123"
    assert author["subtitle"] == "MIT · 40 works"


def test_in_app_records_link_to_their_pages():
    [cand] = gradis_sources.extract_sources(
        "list_candidates",
        {"candidates": [{"id": "c1", "professor_name": "Ada", "school_name": "MIT", "program_name": "EECS", "rationale": "Fits."}]},
    )
    assert cand == {
        "kind": "candidate",
        "id": "c1",
        "title": "Ada",
        "href": "/dossier/c1",
        "subtitle": "MIT · EECS",
        "snippet": "Fits.",
    }
    [app] = gradis_sources.extract_sources(
        "get_application", {"id": "a1", "school": "MIT", "program": "PhD", "deadline": "2026-12-01"}
    )
    assert app["href"] == "/applications/a1" and app["subtitle"] == "PhD · due 2026-12-01"
    [run] = gradis_sources.extract_sources("list_runs", {"runs": [{"id": "r1", "field": "robotics", "region": "US"}]})
    assert run["href"] == "/runs/r1" and run["title"] == "robotics · US"
    [draft] = gradis_sources.extract_sources("list_drafts", {"drafts": [{"id": "d1", "subject": "Hello"}]})
    assert draft["href"] == "/outbox/d1"
    [cv] = gradis_sources.extract_sources("cv_read", {"document_id": "doc1", "name": "My CV", "markdown": "..."})
    assert cv["href"] == "/documents/doc1"
    [prof] = gradis_sources.extract_sources("get_professor", {"id": "p1", "name": "Ada", "candidate_id": None})
    assert prof["href"] == "/professors/p1"
    hits = gradis_sources.extract_sources(
        "search", {"schools": [{"id": "s1", "name": "MIT"}], "programs": [{"id": "g1", "name": "EECS", "school_id": "s1"}]}
    )
    assert [h["href"] for h in hits] == ["/schools/s1", "/schools/s1"]


def test_record_sources_carry_card_media_and_score():
    [candidate] = gradis_sources.extract_sources(
        "get_candidate",
        {"id": "c1", "professor_name": "Ada", "professor_photo_url": "https://img.example/ada.png",
         "similarity_score": 0.91},
    )
    assert candidate["image_url"] == "https://img.example/ada.png"
    assert candidate["score"] == 0.91
    [school] = gradis_sources.extract_sources(
        "get_school", {"id": "s1", "name": "MIT", "image_url": "https://img.example/mit.png"}
    )
    assert school["image_url"] == "https://img.example/mit.png"
    [application] = gradis_sources.extract_sources(
        "get_application", {"id": "a1", "school": "MIT", "program": "PhD Robotics"}
    )
    assert application["program"] == "PhD Robotics"


def test_unknown_tools_errors_and_odd_shapes_register_nothing():
    assert gradis_sources.extract_sources("score_alignment", {"score": 0.8}) == []
    assert gradis_sources.extract_sources("search_web", {"error": "quota"}) == []
    assert gradis_sources.extract_sources("search_web", {"results": "nope"}) == []
    assert gradis_sources.extract_sources("list_runs", "not a dict") == []


def test_registry_keys_are_stable_and_deduped():
    reg = gradis_sources.SourceRegistry()
    a = {"kind": "web", "url": "https://a.example", "title": "A"}
    b = {"kind": "web", "url": "https://b.example", "title": "B"}
    first = reg.register([a, b])
    assert [s["key"] for s in first] == ["s1", "s2"]
    again = reg.register([b, {"kind": "web", "url": "https://c.example", "title": "C"}])
    assert [s["key"] for s in again] == ["s2", "s3"]
    rebuilt = gradis_sources.SourceRegistry.from_events([{"tool": "search_web", "sources": first + again}])
    assert [s["key"] for s in rebuilt.register([a, {"kind": "paper", "title": "P"}])] == ["s1", "s4"]


def test_strip_unknown_keeps_code_and_issued_keys():
    text = "Fact [s1]. Made up [s9]. Both [s1, s9]. Code `x[s9]` stays."
    cleaned, dropped = gradis_sources.strip_unknown(text, {"s1"})
    assert cleaned == "Fact [s1]. Made up. Both [s1]. Code `x[s9]` stays."
    assert dropped == ["s9", "s9"]
    assert gradis_sources.cited_keys("a [s2][s1] b [s2] ```[s5]```") == ["s2", "s1", "s2"]


def _fake_search(results_by_call):
    calls = iter(results_by_call)

    async def handler(tool_input, session, user_id):
        return {"results": next(calls)}

    return handler


def test_citations_persist_and_keys_hold_across_turns(monkeypatch):
    import api.assistant.service as gradis

    a = {"title": "Lab A", "url": "https://a.example.edu", "snippet": "A"}
    b = {"title": "Lab B", "url": "https://b.example.edu", "snippet": "B"}
    c = {"title": "Lab C", "url": "https://c.example.edu", "snippet": "C"}
    monkeypatch.setitem(assistant_tools.HANDLERS, "search_web", _fake_search([[a, b], [b, c]]))
    provider = ScriptProvider(
        [
            ([], [ToolCall(id="t1", name="search_web", arguments={"query": "labs"})]),
            (["Lab A does X [s1]. Lab Z exists [s9]."], []),
            ([], [ToolCall(id="t2", name="search_web", arguments={"query": "more"})]),
            (["Lab C [s3] and Lab B [s2]."], []),
        ]
    )
    monkeypatch.setattr(gradis, "get_provider", lambda: provider)

    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        events = _turn(client, conv_id, "find labs", mode="agent")
        streamed = [p for k, p in events if k == "sources"]
        assert [s["key"] for s in streamed[0]["sources"]] == ["s1", "s2"]
        [message] = [p["message"] for k, p in events if k == "message"]
        assert message["content"] == "Lab A does X [s1]. Lab Z exists."
        assert [s["key"] for s in message["sources"]] == ["s1"]

        tool_msg = next(m for m in provider.seen[1] if m.get("role") == "tool")
        assert "sources:\n[s1] Lab A\n[s2] Lab B" in tool_msg["content"]

        _turn(client, conv_id, "and more?", mode="agent")
        transcript = _transcript(client, conv_id)

    first, second = [m for m in transcript if m["role"] == "assistant"]
    assert [s["key"] for s in first["sources"]] == ["s1"]
    assert [(s["key"], s["url"]) for s in second["sources"]] == [
        ("s3", "https://c.example.edu"),
        ("s2", "https://b.example.edu"),
    ]
    assert first["segments"][-1]["note"] == "Lab A does X [s1]. Lab Z exists."
    assert [m["mode"] for m in transcript if m["role"] == "user"] == ["agent", "agent"]
