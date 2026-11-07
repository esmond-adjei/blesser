"""Small in-process TTL cache with a size bound (LRU eviction), never persisted."""

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Generic, TypeVar

V = TypeVar("V")

#: Every cache made here, so tests can start each case cold.
_ALL: list["TTLCache"] = []


def clear_all() -> None:
    for cache in _ALL:
        cache.clear()


class TTLCache(Generic[V]):
    def __init__(self, maxsize: int, ttl: Callable[[], float]):
        """`ttl` (seconds; <= 0 disables) is read on every lookup, so changes apply at once."""
        self.maxsize = maxsize
        self._ttl = ttl
        self._items: OrderedDict[str, tuple[float, V]] = OrderedDict()
        # Embedding calls run in worker threads (asyncio.to_thread).
        self._lock = threading.Lock()
        _ALL.append(self)

    def get(self, key: str) -> V | None:
        ttl = self._ttl()
        with self._lock:
            hit = self._items.get(key)
            if hit is None or ttl <= 0 or time.monotonic() - hit[0] > ttl:
                return None
            self._items.move_to_end(key)
            return hit[1]

    def put(self, key: str, value: V) -> None:
        if self._ttl() <= 0:
            return
        with self._lock:
            self._items[key] = (time.monotonic(), value)
            self._items.move_to_end(key)
            while len(self._items) > self.maxsize:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        return len(self._items)
