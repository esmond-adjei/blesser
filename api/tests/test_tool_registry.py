import pytest

from api.agent.tools.definitions import TOOL_DEFINITIONS
from api.agent.tools.dispatch import HANDLERS
from api.assistant.tools import ASSISTANT_DEFINITIONS
from api.assistant.tools import HANDLERS as ASSISTANT_HANDLERS


@pytest.mark.parametrize(
    ("definitions", "handlers"),
    [(TOOL_DEFINITIONS, HANDLERS), (ASSISTANT_DEFINITIONS, ASSISTANT_HANDLERS)],
    ids=["worker", "assistant"],
)
def test_handlers_cover_definitions(definitions, handlers):
    assert set(handlers) == {t["name"] for t in definitions}
