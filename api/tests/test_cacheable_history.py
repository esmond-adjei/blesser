"""Compaction moves in blocks so the history's prefix stays cacheable between moves."""

import json

from api.agent.llm.anthropic_provider import AnthropicProvider
from api.agent.orchestrator import _compact_old_tool_results
from api.core.config import settings


def _history(turns: int) -> list[dict]:
    messages = [{"role": "user", "content": "go"}]
    for turn in range(1, turns + 1):
        messages.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"t{turn}", "name": "fetch_page", "arguments": {}}]})
        messages.append({"role": "tool", "tool_call_id": f"t{turn}", "name": "fetch_page", "content": f"page {turn}", "_turn": turn})
    return messages


def test_compaction_moves_in_blocks_so_the_prefix_stays_the_same():
    sent = {}
    for turn in range(3, 10):
        history = _history(turn - 1)  # the history the model sees on `turn`
        sent[turn] = _compact_old_tool_results(history, turn, max_age_turns=2, block_turns=3)
    # Rewritten only when the cutoff moves (turns 5 and 8); in between the prefix is byte-identical.
    moved = [t for t in range(4, 10) if sent[t][: len(sent[t - 1])] != sent[t - 1]]
    assert moved == [5, 8]
    omitted = [m["_turn"] for m in sent[5] if m.get("role") == "tool" and "omitted" in m["content"]]
    assert omitted == [1, 2, 3]
    # A result never outlives max_age + block - 1 turns.
    for turn, history in sent.items():
        for m in history:
            if m.get("role") == "tool" and "omitted" not in m["content"]:
                assert turn - m["_turn"] <= 2 + 3 - 1


def test_block_size_comes_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "compaction_block_turns", 1)
    out = _compact_old_tool_results(_history(3), current_turn=4, max_age_turns=2)
    assert [m["content"] for m in out if m.get("role") == "tool"][:2] == [
        "[fetch_page result already used - omitted]",
        "[fetch_page result already used - omitted]",
    ]


def test_the_end_of_the_history_carries_a_cache_breakpoint(monkeypatch):
    provider = AnthropicProvider(api_key="k", model="claude-x")
    native = provider._to_native_messages(_history(2))
    *earlier, last = native
    assert last["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in json.dumps(earlier)
    native = provider._to_native_messages([{"role": "user", "content": "hello"}])
    assert native == [{"role": "user", "content": [{"type": "text", "text": "hello", "cache_control": {"type": "ephemeral"}}]}]
    monkeypatch.setattr(settings, "llm_prompt_cache", False)
    assert "cache_control" not in json.dumps(provider._to_native_messages(_history(2)))
