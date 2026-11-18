import asyncio
import logging
from contextlib import aclosing

log = logging.getLogger(__name__)


class LiveTurn:
    def __init__(self, user_id):
        self.user_id = user_id
        self.events = []
        self.changed = asyncio.Event()
        self.done = False
        self.task: asyncio.Task | None = None

    def push(self, event):
        self.events.append(event)
        self.wake()

    def wake(self):
        self.changed.set()
        self.changed = asyncio.Event()

    async def follow(self):
        index = 0
        while True:
            while index < len(self.events):
                yield self.events[index]
                index += 1
            if self.done:
                return
            try:
                await asyncio.wait_for(self.changed.wait(), timeout=15)
            except TimeoutError:
                yield {"event": "heartbeat"}


_live: dict[str, LiveTurn] = {}


def get(chat_id, user_id):
    turn = _live.get(chat_id)
    return turn if turn and turn.user_id == user_id else None


def start(chat_id, user_id, events):
    turn = LiveTurn(user_id)
    _live[chat_id] = turn

    async def drive():
        try:
            async with aclosing(events) as stream:
                async for event in stream:
                    turn.push(event)
        except asyncio.CancelledError:
            turn.push({"event": "stopped"})
            raise
        except Exception:
            log.exception("Assistant turn failed")
            turn.push(
                {
                    "event": "error",
                    "message": "The Assistant couldn't finish this reply. Try again.",
                }
            )
        finally:
            turn.done = True
            turn.wake()
            if _live.get(chat_id) is turn:
                del _live[chat_id]

    turn.task = asyncio.create_task(drive(), name=f"assistant-turn-{chat_id}")
    return turn


async def stop(chat_id, user_id):
    turn = get(chat_id, user_id)
    if not turn or not turn.task:
        return False
    if not turn.task.cancelling():
        turn.task.cancel()
    await asyncio.wait([turn.task], timeout=5)
    return True
