"""Spawning keeps listing order, so the supervisor prompt asks for the most promising faculty first."""

from api.prospects import prompts


def test_supervisor_prompt_orders_names_and_spawns_once():
    text = prompts.RESEARCH_PROFESSOR_SYSTEM_PROMPT
    lowered = text.lower()
    assert "most-promising" in lowered and "research-active" in lowered
    for keyword in ("emeritus", "adjunct", "teaching-only"):
        assert keyword in lowered
    assert "spawn_professor_research ONCE" in text
    assert "Do not fabricate professor names" in text
