import asyncio
import logging

from api.assistant.routes import _event_stream


class BadRequestError(Exception):
    status_code = 400


async def _failing_turn():
    yield {"event": "token", "text": "hi"}
    raise BadRequestError("Your credit balance is too low. MARKER-BODY")


def test_failed_turn_is_logged_and_summarised(caplog):
    async def collect():
        return [frame async for frame in _event_stream(_failing_turn())]

    with caplog.at_level(logging.WARNING, logger="api.assistant.routes"):
        frames = asyncio.run(collect())

    assert "MARKER-BODY" in caplog.text
    error = frames[-1]
    assert error.startswith("event: error") and "out of credit" in error and "MARKER" not in error
