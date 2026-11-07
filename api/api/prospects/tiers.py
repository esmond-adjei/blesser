"""School tiers: which selectivity bands discovery should target.

Left alone, discovery clusters at the most famous schools. With several
tiers chosen the programme cap is split evenly so none crowds the others
out. A tier is the model's judgment, a steer, not a guarantee of odds.
"""

from __future__ import annotations

import json
import math

#: key -> (label, how discovery should place a school in it)
TIERS: dict[str, tuple[str, str]] = {
    "top": (
        "Top",
        (
            "the most selective, globally top-ranked research universities "
            "(roughly the world top 50 or a country's top handful)"
        ),
    ),
    "strong": (
        "Strong",
        (
            "highly ranked research universities below the very top "
            "(roughly world rank 50-200)"
        ),
    ),
    "solid": (
        "Solid",
        "well-regarded research-active universities (roughly world rank 200-500)",
    ),
    "accessible": (
        "Accessible",
        (
            "less selective or regional universities that still run research "
            "programmes in the field (beyond roughly world rank 500, or unranked)"
        ),
    ),
}


def normalize(tiers) -> list[str]:
    """Valid tier keys in canonical order, deduped."""
    chosen = {str(t).strip().lower() for t in tiers or []}
    return [key for key in TIERS if key in chosen]


def load(run) -> list[str]:
    """The run's stored tiers ([] = no preference)."""
    raw = getattr(run, "school_tiers", None)
    if not raw:
        return []
    try:
        return normalize(json.loads(raw))
    except (TypeError, ValueError):
        return []


def dump(tiers) -> str | None:
    chosen = normalize(tiers)
    return json.dumps(chosen) if chosen else None


def quotas(tiers: list[str], cap: int) -> dict[str, int]:
    """Each tier's share of the programme cap, rounded up."""
    if not tiers:
        return {}
    share = math.ceil(cap / len(tiers))
    return {t: share for t in tiers}


def brief(tiers: list[str], cap: int) -> str:
    """The discovery brief's tier block ('' when the run has none)."""
    if not tiers:
        return ""
    lines = [f"- {t}: {TIERS[t][1]}" for t in tiers]
    if len(tiers) == 1:
        target = f"Only save schools in the {tiers[0]} tier."
    else:
        share = quotas(tiers, cap)[tiers[0]]
        target = (
            f"Balance the list across these tiers: at most {share} schools per "
            "tier, and cover every tier before filling any one of them. Do not "
            "default to the most famous schools."
        )
    return (
        "School tiers the student is targeting:\n"
        + "\n".join(lines)
        + f"\n{target} Pass each school's tier as school_tier in save_program; "
        "judge it from published rankings and selectivity."
    )


#: Most discovery tasks one run starts in parallel.
MAX_SHARDS = 4


def _regions(run) -> list[str]:
    raw = getattr(run, "region", "") or ""
    parts = [r.strip() for r in raw.split(",") if r.strip()]
    return [] if any(p.lower() == "anywhere" for p in parts) else parts


def discovery_shards(run) -> list[str | None]:
    """Parallel discovery tasks: one per tier when several, else one per
    region when 2..MAX_SHARDS, else [None]. Stored as target_name."""
    chosen = load(run)
    if len(chosen) > 1:
        return [f"tier:{t}" for t in chosen]
    regions = _regions(run)
    if 1 < len(regions) <= MAX_SHARDS:
        return [f"region:{r}" for r in regions]
    return [None]


def shard_share(run, shard: str | None, cap: int) -> int:
    """Schools this shard may save: its even share of the programme cap."""
    shards = discovery_shards(run)
    if shard is None or len(shards) < 2:
        return cap
    return math.ceil(cap / len(shards))
