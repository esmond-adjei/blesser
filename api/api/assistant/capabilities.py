"""Chat controls supported by the configured provider and model."""

import re


def effort_levels(provider: str, model: str) -> list[str]:
    if (
        provider == "openai"
        and re.match(r"^(gpt-5|o3(?:-|$)|o4-mini)", model)
        and "pro" not in model
    ):
        if re.match(r"^gpt-5\.(?:[2-9]|[1-9]\d)(?:-|$)", model):
            return ["low", "medium", "high", "xhigh"]
        return ["low", "medium", "high"]
    if provider == "anthropic" and re.match(
        r"^claude-(opus-4-[56]|sonnet-4-6)(-|$)", model
    ):
        return ["low", "medium", "high"]
    return []
