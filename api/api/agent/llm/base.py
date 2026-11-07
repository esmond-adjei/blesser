"""Model-agnostic LLM provider abstraction.

Message history:
    {"role": "user", "content": str}
    {"role": "assistant", "content": str, "tool_calls": [{"id","name","arguments","extra_content"}]}
    {"role": "tool", "tool_call_id": str, "name": str, "content": str}
`extra_content` replays verbatim (Gemini rejects follow-up turns without its thought signatures).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict = field(default_factory=dict)
    extra_content: dict = field(default_factory=dict)


#: Claude's signed thinking blocks go back to Anthropic unchanged and to no one else.
ANTHROPIC_THINKING = "anthropic_thinking"


def foreign_extras(extra: dict | None, provider: str) -> dict:
    if provider == "anthropic":
        return dict(extra or {})
    return {k: v for k, v in (extra or {}).items() if k != ANTHROPIC_THINKING}


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    truncated: bool = False
    # Shown to the student; never sent back to the model.
    reasoning: str = ""

    @property
    def empty_at_limit(self) -> bool:
        """Cut off before saying or doing anything: ask again with ROOMY_MAX_TOKENS."""
        return self.truncated and not self.text.strip() and not self.tool_calls


ROOMY_MAX_TOKENS = 16_384


class BaseLLMProvider:
    name: str = "base"
    # The backend 400s on tool calls without replayed extras (Gemini thought signatures).
    requires_tool_call_extras: bool = False

    async def chat(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = 4096,
    ) -> LLMResponse:
        raise NotImplementedError


def to_anthropic_tools(tools: list[dict]) -> list[Any]:
    return [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
        }
        for t in tools
    ]


def cached_input_usage(input_tokens: int, cache_read: int, cache_write: int = 0) -> dict:
    """`input_tokens` stays the whole prompt, so totals compare across providers."""
    usage = {"input_tokens": input_tokens}
    if cache_read:
        usage["cache_read_tokens"] = cache_read
    if cache_write:
        usage["cache_write_tokens"] = cache_write
    return usage


def to_openai_tools(tools: list[dict]) -> list[Any]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


#: SDK exception class names that mean "try again later" (openai and anthropic share most).
_TRANSIENT_NAMES = {
    "APITimeoutError",
    "APIConnectionError",
    "RateLimitError",
    "InternalServerError",
    "OverloadedError",
    "ServiceUnavailableError",
}
_TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504, 529}


def is_transient(exc: BaseException) -> bool:
    """Timeouts, dropped connections, rate limits and upstream 5xx."""
    import httpx

    if isinstance(exc, (TimeoutError, ConnectionError, httpx.TimeoutException)):
        return True
    if isinstance(exc, (httpx.ConnectError, httpx.RemoteProtocolError)):
        return True
    if any(cls.__name__ in _TRANSIENT_NAMES for cls in type(exc).__mro__):
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and status in _TRANSIENT_STATUS
