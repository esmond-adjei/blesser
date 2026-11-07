"""Anthropic (Claude) provider."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from api.agent.llm.base import (
    ANTHROPIC_THINKING,
    BaseLLMProvider,
    LLMResponse,
    ToolCall,
    cached_input_usage,
    to_anthropic_tools,
)

_EPHEMERAL = {"type": "ephemeral"}

logger = logging.getLogger(__name__)


def _thinking_config(model: str) -> dict | None:
    """Adaptive thinking with summaries on models that take it (4.6+, Haiku 5+)."""
    match = re.search(r"claude-(opus|sonnet|haiku|fable|mythos)-(\d+)(?:-(\d{1,2}))?(?!\d)", model)
    if not match:
        return None
    family, version = match.group(1), (int(match.group(2)), int(match.group(3) or 0))
    if version >= (4, 7) and (family != "haiku" or version >= (5, 0)):
        return {"type": "adaptive", "display": "summarized"}
    if version == (4, 6) and family != "haiku":
        return {"type": "adaptive"}  # summarized is its default
    return None


def _keep_thinking(tool_calls: list[ToolCall], blocks: list[dict]) -> None:
    """Thinking blocks ride on the first tool call; the tool loop must send them back unchanged."""
    if tool_calls and blocks:
        tool_calls[0].extra_content[ANTHROPIC_THINKING] = blocks


def _thinking_refused(exc: Exception, messages: list[dict]) -> bool:
    """A 400 about thinking blocks this request sent back."""
    replayed = any(
        (tc.get("extra_content") or {}).get(ANTHROPIC_THINKING)
        for m in messages
        for tc in (m.get("tool_calls") or [])
    )
    return replayed and "thinking" in str(exc).lower()


def _usage(usage: Any) -> dict:
    """Fold cached tokens back in so input_tokens is the whole prompt, as elsewhere."""
    fresh = getattr(usage, "input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return cached_input_usage(fresh + read + write, read, write)


def _current_thinking(native: list[Any], replay: bool) -> list[Any]:
    """Only the current tool loop's thinking blocks: each is bound to the conversation before it.

    Dropping them from the front is allowed, from the middle is not.
    """
    fresh = [
        i
        for i, m in enumerate(native)
        if m["role"] == "user"
        and not (
            isinstance(m["content"], list)
            and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"])
        )
    ]
    since = fresh[-1] if fresh and replay else len(native)
    out = []
    for i, m in enumerate(native):
        if m["role"] == "assistant" and i < since and isinstance(m["content"], list):
            content = [b for b in m["content"] if b.get("type") not in ("thinking", "redacted_thinking")]
            m = {**m, "content": content or "..."}
        out.append(m)
    return out


class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def __init__(self, model: str, api_key: str, max_tokens: int = 4096):
        self.effort: str | None = None
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        # Cleared once the API refuses replayed thinking (e.g. compacted history).
        self.replay_thinking = True
        self._client = None

    def _client_or_raise(self):
        if not self.api_key:
            raise RuntimeError(
                "Anthropic API key is missing. Set LLM_API_KEY in .env "
                "(or switch LLM_PROVIDER to ollama/openai/gemini)."
            )
        if self._client is None:
            import anthropic

            from api.core.config import settings

            self._client = anthropic.AsyncAnthropic(
                api_key=self.api_key,
                timeout=settings.llm_timeout_seconds,
                max_retries=2,
            )
        return self._client

    def _prompt(self, system: str, tools: list[dict]) -> dict:
        """System and tools, with a cache breakpoint: they are identical on every turn."""
        from api.core.config import settings

        native_tools = to_anthropic_tools(tools)
        if not native_tools:
            if not settings.llm_prompt_cache or not system:
                return {"system": system}
            return {"system": [{"type": "text", "text": system, "cache_control": _EPHEMERAL}]}
        if not settings.llm_prompt_cache:
            return {"system": system, "tools": native_tools}
        if native_tools:
            native_tools[-1] = {**native_tools[-1], "cache_control": _EPHEMERAL}
        blocks: Any = (
            [{"type": "text", "text": system, "cache_control": _EPHEMERAL}]
            if system
            else system
        )
        return {"system": blocks, "tools": native_tools}

    def _to_native_messages(self, messages: list[dict], replay_thinking: bool = True) -> list[Any]:
        """The last block carries a cache breakpoint: the next turn's history starts with it."""
        from api.core.config import settings

        native = _current_thinking(self._native_messages(messages), replay_thinking)
        if settings.llm_prompt_cache and native:
            last = native[-1]
            content = last["content"]
            if isinstance(content, str):
                # An empty text block is refused; leave such a message be.
                content = [{"type": "text", "text": content}] if content else []
            if content:
                content = [*content[:-1], {**content[-1], "cache_control": _EPHEMERAL}]
                native[-1] = {**last, "content": content}
        return native

    def _native_messages(self, messages: list[dict]) -> list[Any]:
        native: list[Any] = []
        pending_tool_results: list[Any] = []
        # Student words sent during tool runs join the tool results' user turn.
        extra_user_text: list[str] = []

        def flush_tool_results():
            if pending_tool_results:
                content = pending_tool_results.copy()
                if extra_user_text:
                    content.append({"type": "text", "text": "\n\n".join(extra_user_text)})
                    extra_user_text.clear()
                native.append({"role": "user", "content": content})
                pending_tool_results.clear()

        for m in messages:
            role = m.get("role")
            if role == "tool":
                pending_tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": m.get("tool_call_id", ""),
                        "content": str(m.get("content", "")),
                    }
                )
            elif role == "assistant":
                flush_tool_results()
                tool_calls = m.get("tool_calls") or []
                content_blocks: list[dict] = [
                    dict(block)
                    for tc in tool_calls
                    for block in (tc.get("extra_content") or {}).get(ANTHROPIC_THINKING) or []
                ]
                if m.get("content"):
                    content_blocks.append({"type": "text", "text": m["content"]})
                for tc in tool_calls:
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "input": tc.get("arguments", {}),
                        }
                    )
                native.append({"role": "assistant", "content": content_blocks or "..."})
            else:  # user
                if m.get("attachments"):
                    from api.assistant.attachments import user_blocks
                    flush_tool_results()
                    native.append({"role": "user", "content": user_blocks(m, "anthropic")})
                    continue
                text = str(m.get("content", ""))
                if pending_tool_results:
                    extra_user_text.append(text)
                    continue
                flush_tool_results()
                last = native[-1] if native else None
                if (
                    last
                    and last.get("role") == "user"
                    and isinstance(last.get("content"), str)
                ):
                    # Two user turns in a row: Anthropic wants one.
                    native[-1] = {"role": "user", "content": last["content"] + "\n\n" + text}
                    continue
                native.append({"role": "user", "content": text})
        flush_tool_results()
        return native

    def _request(
        self, messages: list[dict], system: str, tools: list[dict], max_tokens: int, replay: bool
    ) -> dict:
        thinking = _thinking_config(self.model)
        return {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            **({"output_config": {"effort": self.effort}} if self.effort else {}),
            **({"thinking": thinking} if thinking else {}),
            "messages": self._to_native_messages(messages, replay_thinking=replay),
            **self._prompt(system, tools),
        }

    async def chat_stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = 4096,
    ):
        """Native streaming; tool_use blocks are reassembled from input_json fragments."""
        import anthropic

        yielded = False
        try:
            async for event in self._stream_once(self._request(messages, system, tools, max_tokens, self.replay_thinking)):
                yielded = True
                yield event
        except anthropic.BadRequestError as exc:
            if yielded or not self.replay_thinking or not _thinking_refused(exc, messages):
                raise
            self.replay_thinking = False
            # Thinking refused (its prefix changed): once more without it.
            logger.warning("Anthropic refused replayed thinking; asking without it: %s", exc)
            async for event in self._stream_once(self._request(messages, system, tools, max_tokens, False)):
                yield event

    async def _stream_once(self, request: dict):
        client = self._client_or_raise()
        text_parts: list[str] = []
        thought_parts: list[str] = []
        calls: dict[int, dict] = {}
        thinking: dict[int, dict] = {}
        usage_out = 0
        stop = None
        usage_start: dict = {"input_tokens": 0}
        async with client.messages.stream(**request) as stream:
            async for event in stream:
                kind = getattr(event, "type", "")
                if kind == "content_block_start":
                    block = getattr(event, "content_block", None)
                    block_type = getattr(block, "type", "")
                    index = getattr(event, "index", 0)
                    if block_type == "tool_use":
                        calls[index] = {
                            "id": getattr(block, "id", ""),
                            "name": getattr(block, "name", ""),
                            "arguments": "",
                        }
                    elif block_type == "thinking":
                        thinking[index] = {"type": "thinking", "thinking": "", "signature": ""}
                    elif block_type == "redacted_thinking":
                        thinking[index] = {"type": "redacted_thinking", "data": getattr(block, "data", "")}
                elif kind == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    delta_kind = getattr(delta, "type", "")
                    index = getattr(event, "index", 0)
                    if delta_kind == "text_delta":
                        text = getattr(delta, "text", "")
                        if text:
                            text_parts.append(text)
                            yield {"type": "token", "text": text}
                    elif delta_kind == "thinking_delta":
                        thought = getattr(delta, "thinking", "")
                        if index in thinking:
                            thinking[index]["thinking"] += thought
                        if thought:
                            thought_parts.append(thought)
                            yield {"type": "reasoning", "text": thought}
                    elif delta_kind == "signature_delta":
                        if index in thinking:
                            thinking[index]["signature"] += getattr(delta, "signature", "")
                    elif delta_kind == "input_json_delta":
                        slot = calls.get(index)
                        if slot is not None:
                            slot["arguments"] += getattr(delta, "partial_json", "")
                elif kind == "message_delta":
                    delta_usage = getattr(
                        getattr(event, "usage", None), "output_tokens", 0
                    )
                    usage_out = delta_usage or usage_out
                    stop = getattr(getattr(event, "delta", None), "stop_reason", None) or stop
                elif kind == "message_start":
                    start_usage = getattr(
                        getattr(event, "message", None), "usage", None
                    )
                    if start_usage is not None:
                        usage_start = _usage(start_usage)
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
                ToolCall(id=slot["id"], name=slot["name"], arguments=args)
            )
        _keep_thinking(tool_calls, [thinking[i] for i in sorted(thinking)])
        yield {
            "type": "done",
            "response": LLMResponse(
                text="".join(text_parts),
                tool_calls=tool_calls,
                usage={**usage_start, "output_tokens": usage_out},
                truncated=stop == "max_tokens",
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
        import anthropic

        client = self._client_or_raise()
        try:
            response = await client.messages.create(
                **self._request(messages, system, tools, max_tokens, self.replay_thinking)
            )
        except anthropic.BadRequestError as exc:
            if not self.replay_thinking or not _thinking_refused(exc, messages):
                raise
            self.replay_thinking = False
            logger.warning("Anthropic refused replayed thinking; asking without it: %s", exc)
            response = await client.messages.create(**self._request(messages, system, tools, max_tokens, False))
        text_parts: list[str] = []
        thought_parts: list[str] = []
        thinking: list[dict] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "thinking":
                thought_parts.append(block.thinking)
                thinking.append({"type": "thinking", "thinking": block.thinking, "signature": block.signature})
            elif block.type == "redacted_thinking":
                thinking.append({"type": "redacted_thinking", "data": block.data})
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id, name=block.name, arguments=dict(block.input or {})
                    )
                )
        _keep_thinking(tool_calls, thinking)
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            usage={
                **_usage(usage),
                "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            },
            truncated=getattr(response, "stop_reason", None) == "max_tokens",
            reasoning="".join(thought_parts),
        )
