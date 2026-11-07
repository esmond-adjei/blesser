"""Agent admin routes: the tool registry and task switches."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.agents import groups as agents_groups
from api.agents import registry as agents_registry
from api.agents import schemas as agents_schemas
from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session
from api.core.exceptions import NotFoundError

router = APIRouter(tags=["agents"])


@router.get("/agent/tools", response_model=list[agents_schemas.AgentToolOut])
async def list_tools(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Every known tool per scope with its switches; missing rows seed on first read."""
    return [
        agents_schemas.AgentToolOut(**d)
        for d in await agents_registry.list_tools(session, current.id)
    ]


@router.patch("/agent/tools/{scope}/{name}", response_model=agents_schemas.AgentToolOut)
async def update_tool(
    scope: str,
    name: str,
    req: agents_schemas.AgentToolUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Flip a tool's switches; takes effect on the next turn."""
    updated = await agents_registry.update_tool(
        session, current.id, scope, name, req.model_dump(exclude_unset=True)
    )
    if updated is None:
        raise NotFoundError("Tool not found")
    return agents_schemas.AgentToolOut(**updated)


@router.get("/agent/tool-groups", response_model=list[agents_schemas.AgentToolGroupOut])
async def list_tool_groups(
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Tools that toggle together, with their members by name."""
    return [agents_schemas.AgentToolGroupOut(**g) for g in agents_groups.list_groups()]


@router.patch(
    "/agent/tool-groups/{scope}/{group_id}",
    response_model=list[agents_schemas.AgentToolOut],
)
async def update_tool_group(
    scope: str,
    group_id: str,
    req: agents_schemas.AgentToolGroupUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Switch every member of a group in one scope atomically."""
    updated = await agents_registry.update_group(
        session, current.id, scope, group_id, req.model_dump(exclude_unset=True)
    )
    if updated is None:
        raise NotFoundError("Tool group not found")
    return [agents_schemas.AgentToolOut(**t) for t in updated]


@router.get("/agent/fallbacks")
async def list_fallbacks(current: auth_schemas.UserOut = Depends(get_current_user)):
    """External dependencies the agent flows rely on, with their fallbacks."""
    from api.candidates.scoring import get_embedding_info
    from api.core.config import settings
    from api.prospects import sources, web

    embedding = get_embedding_info()["embedding_provider"]
    fetch = ["direct", *[n for n in web._fetch_chain() if n != "direct"]]
    return [
        {
            "capability": "search",
            "label": "Web search",
            "used_by": ["discovery", "chat"],
            "chain": [
                *web.search_chain(),
                {"name": "recent results cache", "configured": True},
            ],
            "when_all_fail": "The agent is told search is down and works from known URLs.",
        },
        {
            "capability": "fetch",
            "label": "Read a web page",
            "used_by": ["discovery", "research", "chat"],
            "chain": [{"name": n, "configured": True} for n in fetch],
            "when_all_fail": "Returns guidance text; the agent tries another source.",
        },
        {
            "capability": "scholarly",
            "label": "Publication records",
            "used_by": ["research", "chat"],
            "chain": [
                {"name": "faculty-page ORCID / DBLP ids", "configured": sources.enabled("faculty_page")},
                {"name": "openalex (with retries)", "configured": True},
                {"name": "dblp (computing fields)", "configured": sources.enabled("dblp")},
                {"name": "nih reporter (US schools)", "configured": sources.enabled("nih")},
                {"name": "nsf awards (US schools)", "configured": sources.enabled("nsf")},
                {"name": "orcid (any field)", "configured": sources.enabled("orcid")},
                {"name": "semantic scholar abstracts", "configured": sources.enabled("semantic_scholar")},
            ],
            "when_all_fail": "The agent must not invent papers: it saves the professor "
            "unverified or says publications couldn't be checked.",
        },
        {
            "capability": "embeddings",
            "label": "Fit scoring",
            "used_by": ["research", "chat"],
            "chain": [
                {
                    "name": embedding,
                    "configured": embedding == "local"
                    or bool(settings.resolve_embedding_api_key())
                    or embedding == "ollama",
                },
                {"name": "tf-idf (local)", "configured": True},
            ],
            "when_all_fail": "Scores fall back to local TF-IDF similarity.",
        },
        {
            "capability": "llm",
            "label": "Model",
            "used_by": ["discovery", "research", "drafting", "chat"],
            "chain": [{"name": "your active model", "configured": True}],
            "when_all_fail": "Turns fail visibly and can be retried (chat) or re-run (tasks).",
        },
    ]


@router.get("/agent/tasks", response_model=list[agents_schemas.AgentTaskOut])
async def list_tasks(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """The four research task types with their switches and allowlists."""
    return [
        agents_schemas.AgentTaskOut(**d)
        for d in await agents_registry.list_tasks(session, current.id)
    ]


@router.patch("/agent/tasks/{task_type}", response_model=agents_schemas.AgentTaskOut)
async def update_task(
    task_type: str,
    req: agents_schemas.AgentTaskUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Switch a task type or set its tool allowlist (empty clears it)."""
    updated = await agents_registry.update_task(
        session, current.id, task_type, req.model_dump(exclude_unset=True)
    )
    if updated is None:
        raise NotFoundError("Task type not found")
    return agents_schemas.AgentTaskOut(**updated)
