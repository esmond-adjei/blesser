from datetime import datetime

from pydantic import BaseModel, Field


class ProviderConfigOut(BaseModel):
    provider: str
    model: str = ""
    base_url: str = ""
    context_window: int | None = None
    has_key: bool = False
    is_active: bool = False
    enabled: bool = True
    updated_at: datetime | None = None


class ProviderConfigUpdate(BaseModel):
    """PATCH semantics. An empty-string key clears the stored key; omitted leaves it."""

    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    # Null clears the size; omitted leaves it alone.
    context_window: int | None = Field(default=None, ge=1, le=10_000_000)
    is_active: bool | None = None
    enabled: bool | None = None


class ProviderTestOut(BaseModel):
    ok: bool
    models: list[str] = []
    count: int = 0
    error: str | None = None


class ProviderCatalogEntry(BaseModel):
    provider: str
    default_model: str = ""
    default_base_url: str = ""
    key_required: bool = True
    base_url_required: bool = False


class SystemModelOut(BaseModel):
    """Read-only environment fallback behind every user row."""

    provider: str = ""
    model: str = ""
    base_url: str = ""
    key_configured: bool = False
    context_window: int | None = None


class ProviderCatalogOut(BaseModel):
    providers: list[ProviderCatalogEntry] = []
    system: SystemModelOut = SystemModelOut()
