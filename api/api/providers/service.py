"""Provider configuration: storage, factory resolution, connection tests.

Test-connection probes the model-list endpoint and never spends a generation call.
"""

import logging

import httpx
from sqlalchemy import select

from api.core import egress
from api.core.exceptions import BadRequestError, UnprocessableError
from api.core.secrets import SecretUnavailable

log = logging.getLogger(__name__)

from api.providers import models as providers_models

TEST_TIMEOUT_S = 10.0

#: Backend-filled base URLs; empty means no universal default (anthropic uses
#: its SDK default, openai-compatible needs the user's URL).
DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
}

#: Providers that cannot work without a user-supplied key.
KEY_REQUIRED = {"anthropic", "openai", "gemini", "openai-compatible"}


def default_model_for(provider: str) -> str:
    from api.agent.llm.factory import PROVIDER_DEFAULT_MODELS

    return PROVIDER_DEFAULT_MODELS.get(provider, "")


def default_base_url_for(provider: str) -> str:
    """Backend-resolved base URL for a provider ("" when none exists)."""
    return DEFAULT_BASE_URLS.get(provider, "")


def provider_catalog() -> dict:
    """Everything the Add-model form and model picker need, plus the system config."""
    from api.agent.llm.factory import SUPPORTED_PROVIDERS
    from api.core.config import settings

    system_provider = (settings.llm_provider or "anthropic").lower().strip()
    system_model = settings.llm_model or default_model_for(system_provider)
    return {
        "providers": [
            {
                "provider": name,
                "default_model": default_model_for(name),
                "default_base_url": default_base_url_for(name),
                "key_required": name in KEY_REQUIRED,
                "base_url_required": name == "openai-compatible",
            }
            for name in SUPPORTED_PROVIDERS
        ],
        "system": {
            "provider": system_provider,
            "model": system_model,
            "base_url": settings.resolve_llm_base_url() or "",
            "key_configured": bool(settings.llm_api_key),
            "context_window": settings.llm_context_window,
        },
    }


def _default_rows() -> list[dict]:
    from api.agent.llm.factory import SUPPORTED_PROVIDERS

    return [
        {
            "provider": name,
            "model": "",
            "api_key": "",
            "base_url": "",
            "is_active": False,
        }
        for name in SUPPORTED_PROVIDERS
    ]


async def ensure_configs(session, user_id: str | None) -> None:
    """Insert a row per supported provider for the account; existing rows are never
    touched. A None owner seeds nothing."""
    if user_id is None:
        return
    rows = (
        (
            await session.execute(
                select(providers_models.ProviderConfig).where(
                    providers_models.ProviderConfig.user_id == user_id
                )
            )
        )
        .scalars()
        .all()
    )
    have = {r.provider for r in rows}
    for row in _default_rows():
        if row["provider"] not in have:
            session.add(providers_models.ProviderConfig(user_id=user_id, **row))
    await session.commit()


def _out(row: providers_models.ProviderConfig) -> dict:
    return {
        "provider": row.provider,
        "model": row.model,
        "base_url": row.base_url,
        "context_window": row.context_window,
        "has_key": bool(row.api_key),
        "is_active": row.is_active,
        "enabled": row.enabled,
        "updated_at": row.updated_at,
    }


async def list_configs(session, user_id: str) -> list[dict]:
    await ensure_configs(session, user_id)
    rows = (
        (
            await session.execute(
                select(providers_models.ProviderConfig)
                .where(providers_models.ProviderConfig.user_id == user_id)
                .order_by(providers_models.ProviderConfig.provider)
            )
        )
        .scalars()
        .all()
    )
    return [_out(r) for r in rows]


async def update_config(session, user_id: str, provider: str, data: dict) -> dict | None:
    await ensure_configs(session, user_id)
    row = await session.get(
        providers_models.ProviderConfig, {"user_id": user_id, "provider": provider}
    )
    if row is None:
        return None
    if data.get("model") is not None:
        # A new model starts with no context window unless this write gives one.
        if data["model"] != row.model and "context_window" not in data:
            row.context_window = None
        row.model = data["model"]
    if "context_window" in data:
        row.context_window = data["context_window"]
    if data.get("api_key") is not None:
        row.api_key = data["api_key"]
    if data.get("base_url") is not None:
        try:
            row.base_url = egress.validate_provider_base_url(
                data["base_url"], default_base_url_for(provider)
            )
        except ValueError as exc:
            raise UnprocessableError(str(exc)) from exc
    if data.get("is_active") is True:
        # Exactly one active provider per account.
        others = (
            (
                await session.execute(
                    select(providers_models.ProviderConfig).where(
                        providers_models.ProviderConfig.user_id == user_id,
                        providers_models.ProviderConfig.provider != provider,
                    )
                )
            )
            .scalars()
            .all()
        )
        for other in others:
            other.is_active = False
        row.is_active = True
    elif data.get("is_active") is False:
        row.is_active = False
    if data.get("enabled") is not None:
        row.enabled = data["enabled"]
    await session.commit()
    await session.refresh(row)
    return _out(row)


async def resolve_active_config(session, user_id: str | None) -> dict | None:
    """One account's active row with a model set, else None. No seeding: the hot
    path must not write."""
    if user_id is None:
        return None
    row = (
        (
            await session.execute(
                select(providers_models.ProviderConfig).where(
                    providers_models.ProviderConfig.user_id == user_id,
                    providers_models.ProviderConfig.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    active = [r for r in row if r.model and r.enabled]
    if not active:
        return None
    picked = active[0]
    return _row_kwargs(picked)


async def context_window_for(session, user_id: str | None, llm_kwargs: dict) -> int | None:
    """Context window for the model `resolve_llm_kwargs` picked; None when unset or
    the row's model has changed since."""
    from api.core.config import settings

    if not llm_kwargs:
        return settings.llm_context_window
    if user_id is None:
        return None
    row = await session.get(
        providers_models.ProviderConfig,
        {"user_id": user_id, "provider": llm_kwargs.get("provider")},
    )
    if row is None or row.model != llm_kwargs.get("model"):
        return None
    return row.context_window


def _row_kwargs(row: providers_models.ProviderConfig) -> dict:
    return _factory_kwargs(row.provider, row.model, row.api_key, row.base_url)


def _factory_kwargs(provider: str, model: str, api_key: str, base_url: str) -> dict:
    """Factory kwargs for one account's provider row.

    The operator's environment key is used only when the row is the system
    provider at the system base URL; any other blank-key row sends no key, so a
    user-chosen host never receives the operator's credentials.
    """
    kwargs: dict = {"provider": provider, "model": model}
    resolved_base = base_url or default_base_url_for(provider)
    if resolved_base:
        kwargs["base_url"] = resolved_base
    if egress.needs_guard(base_url, default_base_url_for(provider)):
        # User-chosen host: every request passes the public-address check (core/egress.py).
        kwargs["egress_guard"] = True
    if api_key:
        kwargs["api_key"] = api_key
    elif _may_use_operator_key(provider, resolved_base):
        from api.core.config import settings

        kwargs["api_key"] = settings.resolve_llm_api_key()
    else:
        kwargs["api_key"] = ""
    return kwargs


def _may_use_operator_key(provider: str, resolved_base: str) -> bool:
    """True only for a keyless row aimed where the operator's key already goes."""
    from api.core.config import settings

    system_provider = (settings.llm_provider or "anthropic").lower().strip()
    if provider != system_provider:
        return False
    if provider == "anthropic":
        # The Anthropic client ignores base_url, so the key can't be steered elsewhere.
        return True
    system_base = settings.resolve_llm_base_url() or default_base_url_for(provider)
    return _norm_url(resolved_base) == _norm_url(system_base)


def _norm_url(url: str | None) -> str:
    return (url or "").strip().rstrip("/").lower()


async def _get_json(url: str, headers: dict) -> tuple[int, dict | list]:
    async with httpx.AsyncClient(timeout=TEST_TIMEOUT_S) as client:
        resp = await client.get(url, headers=headers)
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, {}


def _model_names(provider: str, payload: dict | list) -> list[str]:
    items = payload.get("data", []) if isinstance(payload, dict) else []
    names = [m.get("id") or m.get("name") for m in items if isinstance(m, dict)]
    if provider == "gemini":
        names = [
            (m.get("name", "").removeprefix("models/"))
            for m in items
            if isinstance(m, dict)
        ]
    return [n for n in names if n][:20]


async def resolve_llm_kwargs(
    session,
    user_id: str | None = None,
    provider: str | None = None,
    *,
    disabled_to_system: bool = False,
) -> dict:
    """Keyword overrides for the LLM factory; empty means the system model.

    A named provider uses that row, `"system"` the environment config; otherwise
    the account's preference applies. A switched-off row is refused, or with
    `disabled_to_system` becomes the system model so a running run keeps working."""
    if session is None:
        return {}
    try:
        if provider is None:
            if not await prefers_own_model(session, user_id):
                return {}
            return await resolve_active_config(session, user_id) or {}
        if provider == "system":
            return {}
        from api.agent.llm.factory import SUPPORTED_PROVIDERS

        if provider not in SUPPORTED_PROVIDERS:
            raise BadRequestError(f"Unknown provider {provider!r}.")
        if user_id is None:
            return {}
        row = await session.get(
            providers_models.ProviderConfig, {"user_id": user_id, "provider": provider}
        )
        if row is None or not row.model:
            raise BadRequestError(
                f"No model configured for {provider!r} — add it in settings first."
            )
        if not row.enabled:
            if disabled_to_system:
                return {}
            raise BadRequestError(
                f"Your {provider!r} model is switched off — turn it on in settings first."
            )
        return _row_kwargs(row)
    except (BadRequestError, SecretUnavailable):
        # An undecryptable saved key must never quietly become the operator's key.
        raise
    except Exception as exc:  # noqa: BLE001 - degrade to environment, never block the loop
        log.warning("provider config unreadable; using environment: %s", exc)
        return {}


async def prefers_own_model(session, user_id: str | None) -> bool:
    if user_id is None:
        return False
    from api.auth import models as auth_models

    user = await session.get(auth_models.User, user_id)
    return bool(user is not None and user.prefer_own_model)


async def default_choice(session, user_id: str) -> str:
    """What an unset model choice means for this account: "system" or its default
    own provider when opted in and usable."""
    if not await prefers_own_model(session, user_id):
        return "system"
    row = (
        (
            await session.execute(
                select(providers_models.ProviderConfig).where(
                    providers_models.ProviderConfig.user_id == user_id,
                    providers_models.ProviderConfig.is_active.is_(True),
                    providers_models.ProviderConfig.enabled.is_(True),
                    providers_models.ProviderConfig.model != "",
                )
            )
        )
        .scalars()
        .first()
    )
    return row.provider if row is not None else "system"


async def run_provider(session, user_id: str, provider: str | None) -> str:
    """The run's stored model choice: "system" or a configured, enabled provider.
    Unset is resolved now so a run never changes model when settings do; anything
    else is refused now rather than failing every task later."""
    if provider in (None, "", "default"):
        return await default_choice(session, user_id)
    await resolve_llm_kwargs(session, user_id, provider)
    return provider


async def test_connection(
    session,
    user_id: str,
    provider: str,
    base_url: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Probe a provider's model list; explicit values win over stored ones.
    Returns ok/models/count or ok False with an error."""
    stored: dict = {}
    if base_url is None or api_key is None:
        row = await session.get(
            providers_models.ProviderConfig, {"user_id": user_id, "provider": provider}
        )
        if row is not None:
            stored = {"base_url": row.base_url, "api_key": row.api_key}
    base = (base_url if base_url is not None else stored.get("base_url")) or ""
    key = api_key if api_key is not None else stored.get("api_key", "")
    default_base = default_base_url_for(provider)
    try:
        base = egress.validate_provider_base_url(base, default_base)
        if base and egress.needs_guard(base, default_base):
            await egress.check_url(f"{base.rstrip('/')}/models")
    except (ValueError, egress.EgressBlocked) as exc:
        return {"ok": False, "models": [], "count": 0, "error": str(exc)}
    except httpx.HTTPError as exc:
        return {"ok": False, "models": [], "count": 0, "error": str(exc)}
    base = base or default_base
    try:
        if provider == "anthropic":
            status, payload = await _get_json(
                "https://api.anthropic.com/v1/models",
                {"x-api-key": key, "anthropic-version": "2023-06-01"},
            )
        elif provider == "openai":
            status, payload = await _get_json(
                f"{base.rstrip('/')}/models", {"Authorization": f"Bearer {key}"}
            )
        elif provider in ("ollama", "openai-compatible"):
            if not base:
                return {
                    "ok": False,
                    "models": [],
                    "count": 0,
                    "error": "Set a base URL first.",
                }
            status, payload = await _get_json(f"{base.rstrip('/')}/models", {})
        elif provider == "gemini":
            status, payload = await _get_json(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key}", {}
            )
        else:
            return {
                "ok": False,
                "models": [],
                "count": 0,
                "error": f"Unknown provider {provider!r}.",
            }
    except (httpx.HTTPError, ValueError) as exc:
        # Some httpx errors (e.g. ConnectTimeout) stringify to "".
        detail = str(exc)[:200] or f"{type(exc).__name__}; host unreachable or timed out"
        return {"ok": False, "models": [], "count": 0, "error": detail}
    if status != 200:
        return {
            "ok": False,
            "models": [],
            "count": 0,
            "error": f"Provider answered {status}; check the key and base URL.",
        }
    names = _model_names(provider, payload)
    return {"ok": True, "models": names, "count": len(names), "error": None}
