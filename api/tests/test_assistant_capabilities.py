from api.assistant.capabilities import effort_levels
from api.assistant.schemas import ChatModelOverride


def test_effort_levels_match_supported_model_variants():
    assert effort_levels("openai", "gpt-5.6-sol") == ["low", "medium", "high", "xhigh"]
    assert effort_levels("openai", "gpt-5.1") == ["low", "medium", "high"]
    assert effort_levels("openai", "gpt-5-pro") == []
    assert effort_levels("anthropic", "claude-sonnet-4-6") == ["low", "medium", "high"]
    assert effort_levels("gemini", "gemini-2.5-pro") == []


def test_highest_effort_passes_chat_request_validation():
    assert ChatModelOverride(provider="openai", effort="xhigh").effort == "xhigh"
