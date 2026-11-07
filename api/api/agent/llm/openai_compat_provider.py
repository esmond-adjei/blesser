"""OpenAI-compatible provider: openai, ollama, gemini and openai-compatible (/v1/chat/completions)."""

from __future__ import annotations

import json
import re
from typing import Any

from api.agent.llm.base import (
    BaseLLMProvider,
    LLMResponse,
    ToolCall,
    cached_input_usage,
    foreign_extras,
    to_openai_tools,
)


def _usage(usage: Any) -> dict:
    """prompt_tokens already includes cached tokens on these servers;
    OpenAI and Gemini report the cached share in prompt_tokens_details."""
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) if details is not None else 0
    return cached_input_usage(getattr(usage, "prompt_tokens", 0) or 0, cached or 0)


def _reasoning(message: Any) -> str:
    """Ollama sends `reasoning`, vLLM and DeepSeek `reasoning_content`."""
    for name in ("reasoning", "reasoning_content"):
        value = getattr(message, name, None)
        if isinstance(value, str) and value:
            return value
    return ""


_THINK_TAGS = {"<think>": "</think>", "<thought>": "</thought>"}


class ThinkSplitter:
    """Splits leading `<think>`/`<thought>` reasoning from a streamed reply.

    `feed` returns (kind, text) pieces; text that might still start a tag waits.
    """

    def __init__(self) -> None:
        self.state = "start"
        self.close = ""
        self.buffer = ""

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        self.buffer += chunk
        out: list[tuple[str, str]] = []
        while self.buffer:
            if self.state == "start":
                head = self.buffer.lstrip()
                opener = next((t for t in _THINK_TAGS if head.startswith(t)), None)
                if opener:
                    self.state, self.close = "thinking", _THINK_TAGS[opener]
                    self.buffer = head[len(opener):]
                    continue
                if not head or any(t.startswith(head) for t in _THINK_TAGS):
                    break  # still could be a tag
                self.state = "text"
            if self.state == "thinking":
                end = self.buffer.find(self.close)
                if end >= 0:
                    if end:
                        out.append(("reasoning", self.buffer[:end]))
                    self.buffer = self.buffer[end + len(self.close):].lstrip()
                    self.state = "text"
                    continue
                # Hold back what could be the start of the closing tag.
                keep = next(
                    (n for n in range(len(self.close) - 1, 0, -1) if self.buffer.endswith(self.close[:n])),
                    0,
                )
                ready = self.buffer[: len(self.buffer) - keep]
                if ready:
                    out.append(("reasoning", ready))
                self.buffer = self.buffer[len(ready):]
                break
            out.append(("text", self.buffer))
            self.buffer = ""
        return out

    def flush(self) -> list[tuple[str, str]]:
        rest, self.buffer = self.buffer, ""
        if not rest:
            return []
        return [("reasoning" if self.state == "thinking" else "text", rest)]


def split_thinking(text: str) -> tuple[str, str]:
    """(reasoning, reply) of a whole reply."""
    splitter = ThinkSplitter()
    pieces = splitter.feed(text) + splitter.flush()
    return (
        "".join(t for k, t in pieces if k == "reasoning"),
        "".join(t for k, t in pieces if k == "text"),
    )


def _gemini_thinks(model: str) -> bool:
    """Gemini 2.5 and later think; earlier models refuse a thinking config."""
    match = re.search(r"gemini-(\d+)(?:\.(\d+))?", model)
    return bool(match) and (int(match.group(1)), int(match.group(2) or 0)) >= (2, 5)


def _tool_call_extra(tc: Any) -> dict:
    """Provider-native extras on a tool call (Gemini thought signatures); {} when none."""
    extra = getattr(tc, "extra_content", None)
    if extra is None:
        try:
            extra = tc.model_dump().get("extra_content")
        except Exception:  # noqa: BLE001 - non-pydantic test doubles
            extra = None
    return extra if isinstance(extra, dict) else {}


class OpenAICompatProvider(BaseLLMProvider):
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        max_tokens: int = 4096,
        provider_label: str = "openai-compatible",
        egress_guard: bool = False,
    ):
        self.effort: str | None = None
        self.model = model
        self.egress_guard = egress_guard
        self.api_key = api_key
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.name = provider_label
        # Only Gemini enforces signature round-trips.
        self.requires_tool_call_extras = provider_label == "gemini"
        self._client = None

    def _thinking(self) -> dict:
        """Gemini sends thought summaries only when asked."""
        if self.name != "gemini" or not _gemini_thinks(self.model):
            return {}
        return {"extra_body": {"extra_body": {"google": {"thinking_config": {"include_thoughts": True}}}}}

    def _client_or_raise(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "The `openai` package is required for "
                    f"LLM_PROVIDER={self.name}. Run `uv sync` / `pip install openai`."
                ) from exc
            from api.core.config import settings

            kwargs: dict = {
                "api_key": self.api_key or "not-needed",
                "timeout": settings.llm_timeout_seconds,
                "max_retries": 2,
            }
            if self.base_url:
                kwargs["base_url"] = self.base_url
            if self.egress_guard:
                import httpx

                from api.core.egress import GuardedTransport

                kwargs["http_client"] = httpx.AsyncClient(
                    transport=GuardedTransport(), timeout=600
                )
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    def _to_native_messages(self, messages: list[dict], system: str) -> list[Any]:
        native: list[Any] = []
        if system:
            native.append({"role": "system", "content": system})
        for m in messages:
            role = m.get("role")
            if role == "assistant":
                tool_calls = m.get("tool_calls") or []
                if tool_calls:
                    rebuilt = []
                    for tc in tool_calls:
                        call: dict = {
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": json.dumps(tc.get("arguments", {})),
                            },
                        }
                        # Gemini thought signatures must round-trip unchanged.
                        extra = foreign_extras(tc.get("extra_content"), self.name)
                        if extra:
                            call["extra_content"] = extra
                        rebuilt.append(call)
                    native.append(
                        {
                            "role": "assistant",
                            "content": m.get("content") or None,
                            "tool_calls": rebuilt,
                        }
                    )
                else:
                    native.append(
                        {"role": "assistant", "content": str(m.get("content", ""))}
                    )
            elif role == "tool":
                native.append(
                    {
                        "role": "tool",
                        "tool_call_id": m.get("tool_call_id", ""),
                        "content": str(m.get("content", "")),
                    }
                )
            else:  # user
                from api.assistant.attachments import user_blocks
                native.append({"role": "user", "content": user_blocks(m, self.name) if m.get("attachments") else str(m.get("content", ""))})
        return native

    async def chat_stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = 4096,
    ):
        """Native streaming; tool calls are reassembled from per-index fragments."""
        client = self._client_or_raise()
        stream = await client.chat.completions.create(
            model=self.model,
            **({"max_completion_tokens": max_tokens or self.max_tokens} if self.name == "openai" and self.model.startswith(("gpt-5", "o1", "o3", "o4")) else {"max_tokens": max_tokens or self.max_tokens}),
            **({"reasoning_effort": self.effort} if self.effort else {}),
            **self._thinking(),
            messages=self._to_native_messages(messages, system),
            # An empty tools array is refused.
            **({"tools": to_openai_tools(tools)} if tools else {}),
            stream=True,
            stream_options={"include_usage": True},
        )
        text_parts: list[str] = []
        thought_parts: list[str] = []
        splitter = ThinkSplitter()
        calls: dict[int, dict] = {}
        usage_in: dict = {"input_tokens": 0}
        usage_out = 0
        finish = None
        async for chunk in stream:
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage_in = _usage(chunk_usage)
                usage_out = chunk_usage.completion_tokens or 0
            for choice in chunk.choices or []:
                finish = getattr(choice, "finish_reason", None) or finish
                delta = choice.delta
                thought = _reasoning(delta)
                if thought:
                    thought_parts.append(thought)
                    yield {"type": "reasoning", "text": thought}
                content = getattr(delta, "content", None)
                for kind, piece in splitter.feed(content) if content else []:
                    if kind == "reasoning":
                        thought_parts.append(piece)
                        yield {"type": "reasoning", "text": piece}
                    else:
                        text_parts.append(piece)
                        yield {"type": "token", "text": piece}
                for tc in getattr(delta, "tool_calls", None) or []:
                    slot = calls.setdefault(
                        tc.index, {"id": "", "name": "", "arguments": "", "extra": {}}
                    )
                    if tc.id:
                        slot["id"] = tc.id
                    slot["extra"].update(_tool_call_extra(tc))
                    fn = tc.function
                    if fn is not None:
                        if fn.name:
                            slot["name"] = fn.name
                        if fn.arguments:
                            slot["arguments"] += fn.arguments
        for kind, piece in splitter.flush():
            (thought_parts if kind == "reasoning" else text_parts).append(piece)
            yield {"type": "reasoning" if kind == "reasoning" else "token", "text": piece}
        tool_calls: list[ToolCall] = []
        for index in sorted(calls):
            slot = calls[index]
            if not slot["name"]:
                continue
            try:
                args = json.loads(slot["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                ToolCall(
                    id=slot["id"],
                    name=slot["name"],
                    arguments=args,
                    extra_content=slot["extra"],
                )
            )
        yield {
            "type": "done",
            "response": LLMResponse(
                text="".join(text_parts),
                tool_calls=tool_calls,
                usage={**usage_in, "output_tokens": usage_out},
                truncated=finish == "length",
                reasoning="".join(thought_parts),
            ),
        }

    async def chat(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = 4096,
    ) -> LLMResponse:
        client = self._client_or_raise()
        response = await client.chat.completions.create(
            model=self.model,
            **({"max_completion_tokens": max_tokens or self.max_tokens} if self.name == "openai" and self.model.startswith(("gpt-5", "o1", "o3", "o4")) else {"max_tokens": max_tokens or self.max_tokens}),
            **({"reasoning_effort": self.effort} if self.effort else {}),
            **self._thinking(),
            messages=self._to_native_messages(messages, system),
            **({"tools": to_openai_tools(tools)} if tools else {}),
        )
        finish = getattr(response.choices[0], "finish_reason", None)
        choice = response.choices[0].message
        inline_thought, text = split_thinking(choice.content or "")
        tool_calls: list[ToolCall] = []
        for tc in choice.tool_calls or []:
            if tc.type != "function":
                continue
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                    extra_content=_tool_call_extra(tc),
                )
            )
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            usage={
                **_usage(usage),
                "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
            },
            truncated=finish == "length",
            reasoning=_reasoning(choice) or inline_thought,
        )
