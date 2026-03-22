"""Thread-safe in-memory cache with TTL support."""

import time
import asyncio
from typing import Any


class TTLCache:
    """Simple TTL cache for storing API responses."""

    def __init__(self, ttl_seconds: int = 10):
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            if key in self._store:
                timestamp, value = self._store[key]
                if time.time() - timestamp < self.ttl:
                    return value
                del self._store[key]
            return None

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            self._store[key] = (time.time(), value)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    def get_all_keys(self) -> list[str]:
        return list(self._store.keys())


cache = TTLCache(ttl_seconds=10)
