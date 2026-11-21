"""The Assistant's tools, as the agent loop sees them. Each area lives in `toolkit`."""

from api.assistant.toolkit import ALL, Applied, Proposal
from api.assistant.toolkit.base import ToolInput
from api.core.exceptions import NotFoundError

TOOLS = {name: (tool.schema, tool.description) for name, tool in ALL.items()}
LABELS = {name: tool.label for name, tool in ALL.items()}
WRITES = frozenset(name for name, tool in ALL.items() if tool.changes)
DELETES = frozenset(name for name, tool in ALL.items() if tool.kind == "delete")
ASK = "ask_member"
PRIVATE_TOOLS = frozenset(
    name for name, tool in ALL.items() if tool.kind == "read" and tool.private
)
CATALOG_TOOLS = frozenset(name for name, tool in ALL.items() if "catalog" in tool.tags)


def definitions(*, catalog_checked, web_allowed, changes_allowed=True):
    return [
        {
            "name": name,
            "description": tool.description,
            "parameters": tool.schema.model_json_schema(),
        }
        for name, tool in ALL.items()
        if (name != "search_web" or (web_allowed and catalog_checked))
        and (tool.kind == "read" or changes_allowed)
    ]


def get(name):
    tool = ALL.get(name)
    if tool is None:
        raise NotFoundError("Unknown tool")
    return tool


async def read(session, user_id, name, args: ToolInput, registry):
    tool = get(name)
    if tool.read is None:
        raise ValueError("Unknown read tool")
    return await tool.read(session, user_id, args, registry)


async def proposal(session, user_id, name, args) -> Proposal:
    tool = get(name)
    if tool.propose is None:
        raise NotFoundError("Unknown action")
    return await tool.propose(session, user_id, args)


async def apply_change(session, user_id, name, arguments) -> Applied:
    tool = get(name)
    if tool.apply is None:
        raise NotFoundError("Unknown action")
    return await tool.apply(session, user_id, arguments)
