"""Provider routes: model selection and BYO keys. Keys are write-only."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session
from api.core.exceptions import NotFoundError
from api.providers import schemas as providers_schemas
from api.providers import service as providers_service

router = APIRouter(tags=["models"])


@router.get("/providers/catalog", response_model=providers_schemas.ProviderCatalogOut)
async def provider_catalog(
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Add-model metadata: provider defaults, requirements and the system fallback (no secrets)."""
    del current
    return providers_schemas.ProviderCatalogOut(**providers_service.provider_catalog())


@router.get("/providers", response_model=list[providers_schemas.ProviderConfigOut])
async def list_providers(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Every supported provider with its model, base URL and key presence; seeds on first read."""
    return [
        providers_schemas.ProviderConfigOut(**d)
        for d in await providers_service.list_configs(session, current.id)
    ]


@router.patch(
    "/providers/{provider}", response_model=providers_schemas.ProviderConfigOut
)
async def update_provider(
    provider: str,
    req: providers_schemas.ProviderConfigUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Set a provider's model, key or base URL, or make it active. An empty key clears it."""
    updated = await providers_service.update_config(
        session, current.id, provider, req.model_dump(exclude_unset=True)
    )
    if updated is None:
        raise NotFoundError("Provider not found")
    return providers_schemas.ProviderConfigOut(**updated)


@router.post(
    "/providers/{provider}/test", response_model=providers_schemas.ProviderTestOut
)
async def test_provider(
    provider: str,
    body: dict | None = None,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Probe a provider's model list (explicit credentials win over stored). Never spends."""
    explicit = body or {}
    result = await providers_service.test_connection(
        session,
        current.id,
        provider,
        base_url=explicit.get("base_url"),
        api_key=explicit.get("api_key"),
    )
    return providers_schemas.ProviderTestOut(**result)
