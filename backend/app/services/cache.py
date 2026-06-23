import time
from collections import OrderedDict
from threading import Lock
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """A small thread-safe in-memory cache with per-entry TTL and LRU eviction.

    The recommendation flow uses this to remember the batch of titles returned
    by a single combined web search so that similar later searches, and the
    "recommend a different movie" flow, can be served without another search.
    """

    def __init__(self, ttl_seconds: float, max_entries: int) -> None:
        self._ttl_seconds = max(0.0, ttl_seconds)
        self._max_entries = max(1, max_entries)
        self._entries: "OrderedDict[str, tuple[float, T]]" = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> T | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= now:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return value

    def set(self, key: str, value: T) -> None:
        expires_at = time.monotonic() + self._ttl_seconds
        with self._lock:
            self._entries[key] = (expires_at, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
