"""Agent flows: the built-in pipeline as data, plus user copies.

Per step a user may turn it off, narrow its tools, or append instructions; never add tools,
raise budgets or skip gates. apply_step() is the single enforcement point.
"""

from api.agents.groups import TOOL_GROUPS
from api.core.exceptions import BadRequestError, NotFoundError

STEP_META = {
    "discover_programs": {
        "label": "Find programmes",
        "summary": "Search for programmes matching the run's field and region.",
    },
    "research_professor": {
        "label": "Find faculty",
        "summary": "Read each programme's faculty listing and queue professors.",
    },
    "research_one_professor": {
        "label": "Research each professor",
        "summary": "Pull publications, score fit, and save the dossier entry.",
    },
    "draft_email": {
        "label": "Draft outreach",
        "summary": "Write a personalised email draft for you to review (never sent).",
    },
}
STEP_ORDER = list(STEP_META)
MAX_INSTRUCTIONS = 1500

BUILTINS = {
    "standard": {
        "id": "standard",
        "name": "Standard research",
        "builtin": True,
        "steps": [
            {
                "type": t,
                "enabled": True,
                "tool_groups": [],
                "tools": [],
                "instructions": "",
            }
            for t in STEP_ORDER
        ],
    }
}


class FlowError(RuntimeError):
    """A custom flow can't run a step; the message says how to fix it."""


def _known_tools() -> set[str]:
    from api.agent.tools.dispatch import HANDLERS

    return set(HANDLERS)


def validate_steps(steps: list[dict]) -> list[dict]:
    """Raises BadRequestError."""
    by_type = {}
    for raw in steps:
        t = raw.get("type")
        if t not in STEP_META:
            raise BadRequestError(f"Unknown step '{t}'.")
        if t in by_type:
            raise BadRequestError(f"Step '{STEP_META[t]['label']}' appears twice.")
        groups = [g for g in raw.get("tool_groups") or []]
        bad_groups = [g for g in groups if g not in TOOL_GROUPS]
        if bad_groups:
            raise BadRequestError(f"Unknown tool group(s): {', '.join(bad_groups)}.")
        tools = [x for x in raw.get("tools") or []]
        bad_tools = [x for x in tools if x not in _known_tools()]
        if bad_tools:
            raise BadRequestError(f"Unknown tool(s): {', '.join(bad_tools)}.")
        instructions = str(raw.get("instructions") or "").strip()
        if len(instructions) > MAX_INSTRUCTIONS:
            raise BadRequestError(
                f"Instructions for '{STEP_META[t]['label']}' are too long "
                f"({len(instructions)} of {MAX_INSTRUCTIONS} characters)."
            )
        by_type[t] = {
            "type": t,
            "enabled": bool(raw.get("enabled", True)),
            "tool_groups": groups,
            "tools": tools,
            "instructions": instructions,
        }
    # Fixed order; steps not mentioned keep the built-in defaults.
    out = [
        by_type.get(t)
        or {
            "type": t,
            "enabled": True,
            "tool_groups": [],
            "tools": [],
            "instructions": "",
        }
        for t in STEP_ORDER
    ]
    if not any(
        s["enabled"]
        for s in out
        if s["type"] in ("research_professor", "research_one_professor")
    ):
        raise BadRequestError("A flow needs at least one research step turned on.")
    return out


def flow_out(row) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "base": row.base,
        "builtin": False,
        "steps": row.steps,
        "updated_at": row.updated_at,
    }


async def get_flow_or_404(session, user_id: str, flow_id: str):
    from api.flows.models import AgentFlow

    row = await session.get(AgentFlow, flow_id)
    if row is None or row.user_id != user_id:
        raise NotFoundError("Flow not found")
    return row


def _allowed_tools(step: dict) -> set[str] | None:
    """None = no narrowing; otherwise the union of groups and tools."""
    names: set[str] = set(step.get("tools") or [])
    for g in step.get("tool_groups") or []:
        names |= set(TOOL_GROUPS.get(g, {}).get("tools", ()))
    return names or None


async def step_for(session, run, task_type: str | None) -> tuple[str, dict] | None:
    """(flow name, step) for this run's custom flow, or None for Standard."""
    flow_id = getattr(run, "flow_id", None)
    if not flow_id or not task_type or session is None:
        return None
    from api.flows.models import AgentFlow

    row = await session.get(AgentFlow, flow_id)
    if row is None:
        return None
    step = next((s for s in row.steps or [] if s.get("type") == task_type), None)
    return (row.name, step) if step else None


def apply_step(flow_name: str, step: dict, system_prompt: str, tools: list[dict]):
    """Narrow tools and extend the prompt for one step; never widens."""
    allowed = _allowed_tools(step)
    if allowed is not None:
        tools = [t for t in tools if t.get("name") in allowed]
        if not tools:
            label = STEP_META[step["type"]]["label"]
            raise FlowError(
                f"Flow '{flow_name}': step '{label}' allows no tools that are enabled for "
                "your account. Edit the flow in Settings > Flows, or turn the tools back "
                "on in Agents & tools."
            )
    if step.get("instructions"):
        system_prompt = (
            f"{system_prompt}\n\n## Additional instructions from the user's flow "
            f"'{flow_name}'\nFollow these unless they conflict with the rules above "
            f"(never invent records, respect budgets).\n{step['instructions']}"
        )
    return system_prompt, tools
