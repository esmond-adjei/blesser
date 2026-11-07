"""Provider factory: LLM_PROVIDER string -> configured provider instance."""

from __future__ import annotations

from api.agent.llm.anthropic_provider import AnthropicProvider
from api.agent.llm.base import BaseLLMProvider
from api.agent.llm.openai_compat_provider import OpenAICompatProvider
from api.core.config import DEFAULT_ANTHROPIC_MODEL

PROVIDER_DEFAULT_MODELS = {
    "anthropic": DEFAULT_ANTHROPIC_MODEL,
    "openai": "gpt-4o-mini",
    "ollama": "llama3.1",
    "gemini": "gemini-2.0-flash",
    "openai-compatible": "gpt-4o-mini",
}

SUPPORTED_PROVIDERS = sorted(PROVIDER_DEFAULT_MODELS)


def _default_model_for(provider: str, configured_model: str) -> str:
    """The configured model, unless it's still the Anthropic default for another provider."""
    if configured_model and configured_model != DEFAULT_ANTHROPIC_MODEL:
        return configured_model
    return PROVIDER_DEFAULT_MODELS.get(provider, configured_model)


def get_provider(
    settings=None,
    *,
    provider=None,
    model=None,
    api_key=None,
    base_url=None,
    egress_guard=False,
) -> BaseLLMProvider:
    """Build the LLM provider; keyword overrides win over env config.

    `egress_guard` routes requests through the public-address check (for user-chosen base URLs).
    """
    if settings is None:
        from api.core.config import settings as app_settings

        settings = app_settings

    provider = (provider or settings.llm_provider or "anthropic").lower().strip()
    model = model or _default_model_for(provider, settings.llm_model)
    max_tokens = settings.llm_max_tokens
    resolved_key = api_key if api_key is not None else settings.resolve_llm_api_key()
    resolved_base = (
        base_url if base_url is not None else settings.resolve_llm_base_url()
    )

    if provider == "anthropic":
        return AnthropicProvider(
            model=model, api_key=resolved_key, max_tokens=max_tokens
        )
    if provider in ("openai", "ollama", "gemini", "openai-compatible"):
        return OpenAICompatProvider(
            model=model,
            api_key=resolved_key,
            base_url=resolved_base,
            max_tokens=max_tokens,
            provider_label=provider,
            egress_guard=egress_guard,
        )
    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. Supported: {', '.join(SUPPORTED_PROVIDERS)}"
    )
