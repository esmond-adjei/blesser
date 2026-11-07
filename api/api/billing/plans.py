"""Plan model: what each tier includes, as data the server enforces (docs/plans.md).

`beta` is not sold: while BILLING_ENFORCED is false every account resolves to
it (all features, no quotas). Gates are features (included or not) and quotas
(monthly or per-run numbers checked against usage), enforced in
api/billing/service.py.
"""

from dataclasses import dataclass, field

FEATURES = {
    "gradis_chat": "Gradis chat assistant",
    "cv_editor": "CV studio",
    "data_export": "Export your data",
    "interest_suggestions": "Interest suggestions from your CV",
}

# How a quota reads in a sentence ("3 research runs a month").
QUOTA_NOUN = {
    "runs_per_month": "research runs",
    "model_tokens_per_month": "model tokens",
    "professors_per_run": "professors per run",
}

QUOTAS = {
    "runs_per_month": "Research runs per month",
    "model_tokens_per_month": "Model tokens per month",
    "professors_per_run": "Professors scored per run",
}


@dataclass(frozen=True)
class Plan:
    id: str
    label: str
    features: frozenset[str]
    quotas: dict[str, int] = field(default_factory=dict)
    # Daily system-model tokens: None follows SYSTEM_MODEL_DAILY_TOKENS, 0 is
    # unlimited. Own models never draw on it.
    system_tokens_per_day: int | None = None
    # Whether the operator's daily ceilings (system tokens, SYSTEM_DAILY_TOOL_CALLS)
    # apply, on top of the monthly quotas.
    daily_ceilings: bool = True
    # Monthly price in whole USD (placeholder until launch); 0 = no payment.
    monthly_price_usd: int = 0
    purchasable: bool = True


_PRO_QUOTAS = {
    "runs_per_month": 30,
    "model_tokens_per_month": 20_000_000,
    "professors_per_run": 100,
}

PLANS: dict[str, Plan] = {
    "free": Plan(
        id="free",
        label="Free",
        features=frozenset({"gradis_chat", "cv_editor", "data_export"}),
        quotas={
            "runs_per_month": 3,
            "model_tokens_per_month": 2_000_000,
            "professors_per_run": 30,
        },
        system_tokens_per_day=500_000,
    ),
    "pro": Plan(
        id="pro",
        label="Pro",
        features=frozenset(FEATURES),
        quotas=_PRO_QUOTAS,
        system_tokens_per_day=0,
        monthly_price_usd=12,
    ),
    # No quotas and no daily ceilings, the operator's included.
    "beta": Plan(
        id="beta",
        label="Beta",
        features=frozenset(FEATURES),
        quotas={},
        daily_ceilings=False,
        purchasable=False,
    ),
}

# Cheapest plan that includes each feature (drives the upgrade prompt).
UPGRADE_TO = "pro"
