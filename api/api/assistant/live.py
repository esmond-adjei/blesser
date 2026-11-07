"""Gradis turns that outlive their request: each runs as a task that keeps
every event, so a reload doesn't cancel it and returning clients replay it.
In memory, as one process serves the API (see service._RUNNING_TURNS).
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable

log = logging.getLogger(__name__)

#: How long stop() waits for a cancelled turn to clean up, so the next
#: prompt doesn't find the chat still busy.
STOP_WAIT_SECONDS = 5.0


class LiveTurn:

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.events: list[dict] = []
        self.done = False
        self.task: asyncio.Task | None = None
        self._changed = asyncio.Event()

    def _push(self, event: dict) -> None:
        self.events.append(event)
        self._wake()

    def _wake(self) -> None:
        # Every follower waiting on the old event wakes; later waits use
        # the new one.
        self._changed.set()
        self._changed = asyncio.Event()

    async def follow(self) -> AsyncIterator[dict]:
        """Every event from the start of the turn, then each new one
        until it ends. Hanging up stops only this follower."""
        index = 0
        while True:
            while index < len(self.events):
                yield self.events[index]
                index += 1
            if self.done:
                return
            await self._changed.wait()


_LIVE: dict[str, LiveTurn] = {}


def get(conversation_id: str) -> LiveTurn | None:
    return _LIVE.get(conversation_id)


def running(conversation_id: str) -> bool:
    return conversation_id in _LIVE


def start(
    conversation_id: str,
    user_id: str,
    events: AsyncIterator[dict],
    on_error: Callable[[Exception], dict],
) -> LiveTurn:
    """Run a turn's event stream as a task. A failure becomes the event
    `on_error` makes of it, so followers see why the turn ended."""
    turn = LiveTurn(user_id)
    _LIVE[conversation_id] = turn

    async def drive() -> None:
        try:
            # Closed on the way out, so the turn's own cleanup (its
            # session, the running flag) runs even when it is stopped.
            async with contextlib.aclosing(events) as stream:  # type: ignore[type-var]
                async for event in stream:
                    turn._push(event)
        except asyncio.CancelledError:
            turn._push({"event": "stopped"})
            raise
        except Exception as exc:  # noqa: BLE001 - followers get an error event, not a hang
            turn._push(on_error(exc))
        finally:
            turn.done = True
            turn._wake()
            if _LIVE.get(conversation_id) is turn:
                del _LIVE[conversation_id]

    turn.task = asyncio.create_task(drive(), name=f"gradis-turn-{conversation_id}")
    return turn


async def stop(conversation_id: str) -> bool:
    """Cancel the chat's running turn and wait briefly for it to clean
    up. False when nothing was running."""
    turn = _LIVE.get(conversation_id)
    if turn is None or turn.task is None:
        return False
    turn.task.cancel()
    await asyncio.wait([turn.task], timeout=STOP_WAIT_SECONDS)
    return True
