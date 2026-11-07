from api.agent.tools.definitions import TOOL_DEFINITIONS
from api.agent.tools.dispatch import HANDLERS


def test_handlers_cover_definitions():
    assert set(HANDLERS) == {t["name"] for t in TOOL_DEFINITIONS}
