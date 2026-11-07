"""Tool registry: rows seeded from code, governed from the UI.

A disabled tool leaves both the model's tool list and the dispatcher.
"""

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.agents import groups as agents_groups
from api.agents import models as agents_models

log = logging.getLogger(__name__)

WORKER_SCOPE = "worker"
ASSISTANT_SCOPE = "assistant"

TASK_TYPES = (
    "discover_programs",
    "research_professor",
    "research_one_professor",
    "draft_email",
    "discover_opportunities",
)

#: Least-privilege allowlists, also used for rows without their own, so empty never means "every tool".
DEFAULT_TASK_TOOLS: dict[str, tuple[str, ...]] = {
    "discover_programs": ("search_web", "fetch_page", "save_program"),
    "research_professor": (
        "search_web",
        "fetch_page",
        "spawn_professor_research",
        "confirm_no_match",
        "save_application",
    ),
    "research_one_professor": (
        "search_web",
        "fetch_page",
        "find_openalex_author",
        "get_author_works",
        "score_alignment",
        "save_professor_record",
        "save_application",
        "confirm_no_match",
    ),
    "draft_email": ("save_email_draft",),
    "discover_opportunities": ("search_web", "fetch_page", "save_opportunity"),
}


def default_task_tools(task_type: str | None) -> list[str]:
    return list(DEFAULT_TASK_TOOLS.get(task_type or "", ()))


def _assistant_definitions() -> list[dict]:
    from api.assistant import tools as assistant_tools

    return list(assistant_tools.ASSISTANT_DEFINITIONS)


def _assistant_handlers() -> dict:
    from api.assistant import tools as assistant_tools

    return dict(assistant_tools.HANDLERS)


def _assistant_confirm() -> set[str]:
    from api.assistant import tools as assistant_tools

    return set(assistant_tools.CONFIRM_TOOLS)


def _worker_definitions() -> list[dict]:
    from api.agent.tools import definitions as tools_definitions

    return list(tools_definitions.TOOL_DEFINITIONS)


def descriptions(scope: str) -> dict[str, str]:
    defs = _worker_definitions() if scope == WORKER_SCOPE else _assistant_definitions()
    return {d["name"]: d.get("description", "") for d in defs if "name" in d}


async def ensure_registry(session, user_id: str | None) -> None:
    """Insert missing rows for the account; existing rows are never touched. None seeds nothing."""
    if user_id is None:
        return
    from api.agent.tools.dispatch import HANDLERS, READ_ONLY_TOOLS

    rows = (
        await session.execute(
            select(agents_models.AgentTool).where(
                agents_models.AgentTool.user_id == user_id
            )
        )
    ).scalars().all()
    have = {(r.name, r.scope) for r in rows}
    tools = [
        {"user_id": user_id, "name": name, "scope": WORKER_SCOPE, "enabled": True,
         "read_only": name in READ_ONLY_TOOLS, "confirm_required": False}
        for name in HANDLERS
        if (name, WORKER_SCOPE) not in have
    ] + [
        {"user_id": user_id, "name": name, "scope": ASSISTANT_SCOPE, "enabled": True,
         "read_only": False, "confirm_required": name in _assistant_confirm()}
        for name in _assistant_handlers()
        if (name, ASSISTANT_SCOPE) not in have
    ]  # fmt: skip
    have_tasks = set(
        (
            await session.execute(
                select(agents_models.AgentTask.task_type).where(
                    agents_models.AgentTask.user_id == user_id
                )
            )
        ).scalars()
    )
    tasks = [
        {"user_id": user_id, "task_type": task_type, "enabled": True,
         "tools": default_task_tools(task_type)}
        for task_type in TASK_TYPES
        if task_type not in have_tasks
    ]  # fmt: skip
    # A new account's parallel discovery shards all seed at once.
    if tools:
        await session.execute(
            pg_insert(agents_models.AgentTool).values(tools).on_conflict_do_nothing()
        )
    if tasks:
        await session.execute(
            pg_insert(agents_models.AgentTask).values(tasks).on_conflict_do_nothing()
        )
    await session.commit()


def reads_only(scope: str, name: str) -> bool:
    """Decided in code, not by the account."""
    if scope == ASSISTANT_SCOPE:
        return name not in _assistant_confirm()
    from api.agent.tools.dispatch import READ_ONLY_TOOLS

    return name in READ_ONLY_TOOLS


async def tool_states(
    session, user_id: str | None, scope: str, names: list[str]
) -> dict[str, dict]:
    """Registry rows for the named tools; anything missing or unreadable means code defaults."""
    if user_id is None:
        return {}
    try:
        rows = (
            (
                await session.execute(
                    select(agents_models.AgentTool).where(
                        agents_models.AgentTool.user_id == user_id,
                        agents_models.AgentTool.scope == scope,
                        agents_models.AgentTool.name.in_(names),
                    )
                )
            )
            .scalars()
            .all()
            if names
            else []
        )
    except Exception as exc:  # noqa: BLE001 - degrade to code defaults, never block the loop
        log.warning("tool registry unreadable; using code defaults: %s", exc)
        return {}
    return {
        r.name: {
            "enabled": r.enabled,
            "read_only": r.read_only,
            "confirm_required": r.confirm_required,
        }
        for r in rows
    }


async def tool_state(session, user_id: str | None, scope: str, name: str) -> dict:
    states = await tool_states(session, user_id, scope, [name])
    return states.get(
        name, {"enabled": True, "read_only": False, "confirm_required": False}
    )


async def list_tools(session, user_id: str) -> list[dict]:
    await ensure_registry(session, user_id)
    rows = (
        (
            await session.execute(
                select(agents_models.AgentTool)
                .where(agents_models.AgentTool.user_id == user_id)
                .order_by(
                    agents_models.AgentTool.scope, agents_models.AgentTool.name
                )
            )
        )
        .scalars()
        .all()
    )
    out = []
    cache: dict[str, dict[str, str]] = {}
    for row in rows:
        if row.scope not in cache:
            cache[row.scope] = descriptions(row.scope)
        out.append(
            {
                "name": row.name,
                "scope": row.scope,
                "enabled": row.enabled,
                "read_only": reads_only(row.scope, row.name),
                "confirm_required": row.confirm_required,
                "description": cache[row.scope].get(row.name, ""),
                "group": agents_groups.group_of(row.name),
                "updated_at": row.updated_at,
            }
        )
    return out


async def update_tool(session, user_id: str, scope: str, name: str, data: dict) -> dict | None:
    await ensure_registry(session, user_id)
    row = await session.get(
        agents_models.AgentTool, {"user_id": user_id, "name": name, "scope": scope}
    )
    if row is None:
        return None
    patch = dict(data)
    patch.pop("name", None)
    patch.pop("scope", None)
    patch.pop("description", None)
    patch.pop("updated_at", None)
    patch.pop("read_only", None)
    for field, value in patch.items():
        if value is not None and hasattr(row, field):
            setattr(row, field, value)
    await session.commit()
    await session.refresh(row)
    return {
        "name": row.name,
        "scope": row.scope,
        "enabled": row.enabled,
        "read_only": reads_only(row.scope, row.name),
        "confirm_required": row.confirm_required,
        "description": descriptions(scope).get(name, ""),
        "group": agents_groups.group_of(row.name),
        "updated_at": row.updated_at,
    }


async def update_group(
    session, user_id: str, scope: str, group_id: str, data: dict
) -> list[dict] | None:
    """One commit, so the model never sees a half-enabled group. None when the scope has no members."""
    group = agents_groups.TOOL_GROUPS.get(group_id)
    if group is None:
        return None
    await ensure_registry(session, user_id)
    rows = (
        (
            await session.execute(
                select(agents_models.AgentTool).where(
                    agents_models.AgentTool.user_id == user_id,
                    agents_models.AgentTool.scope == scope,
                    agents_models.AgentTool.name.in_(group["tools"]),
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    confirmable = _assistant_confirm()
    for row in rows:
        if data.get("enabled") is not None:
            row.enabled = data["enabled"]
        if data.get("confirm_required") is not None and scope == ASSISTANT_SCOPE and row.name in confirmable:
            row.confirm_required = data["confirm_required"]
    await session.commit()
    names = {r.name for r in rows}
    return [t for t in await list_tools(session, user_id) if t["scope"] == scope and t["name"] in names]


async def list_tasks(session, user_id: str) -> list[dict]:
    await ensure_registry(session, user_id)
    rows = (
        (
            await session.execute(
                select(agents_models.AgentTask)
                .where(agents_models.AgentTask.user_id == user_id)
                .order_by(agents_models.AgentTask.task_type)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "task_type": r.task_type,
            "enabled": r.enabled,
            "tools": r.tools or default_task_tools(r.task_type),
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


async def update_task(session, user_id: str, task_type: str, data: dict) -> dict | None:
    await ensure_registry(session, user_id)
    row = await session.get(
        agents_models.AgentTask, {"user_id": user_id, "task_type": task_type}
    )
    if row is None:
        return None
    if data.get("enabled") is not None:
        row.enabled = data["enabled"]
    if data.get("tools") is not None:
        row.tools = list(data["tools"])
    await session.commit()
    await session.refresh(row)
    return {
        "task_type": row.task_type,
        "enabled": row.enabled,
        "tools": row.tools or default_task_tools(row.task_type),
        "updated_at": row.updated_at,
    }


async def task_state(session, user_id: str | None, task_type: str | None) -> dict:
    """Allowlist + switch for one task type; falls back to DEFAULT_TASK_TOOLS, never every tool."""
    defaults = {"enabled": True, "tools": default_task_tools(task_type)}
    if not task_type:
        return defaults
    try:
        await ensure_registry(session, user_id)
        if user_id is None:
            return defaults
        row = await session.get(
            agents_models.AgentTask, {"user_id": user_id, "task_type": task_type}
        )
    except Exception as exc:  # noqa: BLE001 - degrade to code defaults, never block the loop
        log.warning("task registry unreadable; using code defaults: %s", exc)
        return defaults
    if row is None:
        return defaults
    return {"enabled": row.enabled, "tools": row.tools or defaults["tools"]}


async def worker_definitions(
    session, user_id: str | None, task_type: str | None = None
) -> list[dict]:
    """TOOL_DEFINITIONS minus disabled tools and those outside the task's allowlist."""
    defs = _worker_definitions()
    names = [d["name"] for d in defs if "name" in d]
    states = await tool_states(session, user_id, WORKER_SCOPE, names)
    allowed = (await task_state(session, user_id, task_type))["tools"]
    return [
        d
        for d in defs
        if d.get("name")
        and states.get(d["name"], {"enabled": True})["enabled"]
        and (not allowed or d["name"] in allowed)
    ]


async def assistant_definitions(session, user_id: str | None) -> list[dict]:
    defs = _assistant_definitions()
    names = [d["name"] for d in defs if "name" in d]
    states = await tool_states(session, user_id, ASSISTANT_SCOPE, names)
    return [
        d
        for d in defs
        if d.get("name") and states.get(d["name"], {"enabled": True})["enabled"]
    ]


async def assistant_confirm_required(
    session, user_id: str | None, tool_name: str
) -> bool:
    if user_id is None:
        return tool_name in _assistant_confirm()
    from api.auth.models import User

    if await session.scalar(select(User.agent_full_access).where(User.id == user_id)):
        return False
    row = await session.get(
        agents_models.AgentTool,
        {"user_id": user_id, "name": tool_name, "scope": ASSISTANT_SCOPE},
    )
    if row is None:
        return tool_name in _assistant_confirm()
    return bool(row.confirm_required)
