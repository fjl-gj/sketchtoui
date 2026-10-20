from __future__ import annotations

import time
from threading import RLock


class MemoryCache:
    """Process-local implementation of the cache commands used by the app."""

    def __init__(self) -> None:
        self._values: dict[str, tuple[str, float | None]] = {}
        self._lock = RLock()
        self._next_cleanup = 0.0

    def _get(self, key: str) -> tuple[str, float | None] | None:
        value = self._values.get(key)
        if value is not None and value[1] is not None and value[1] <= time.monotonic():
            del self._values[key]
            return None
        return value

    def _cleanup(self) -> None:
        now = time.monotonic()
        if now >= self._next_cleanup:
            self._values = {key: value for key, value in self._values.items() if value[1] is None or value[1] > now}
            self._next_cleanup = now + 60

    def get(self, key: str) -> str | None:
        with self._lock:
            value = self._get(key)
            return value[0] if value is not None else None

    def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool | None:
        if ex is not None and ex <= 0:
            raise ValueError("Cache expiration must be positive")
        with self._lock:
            self._cleanup()
            if nx and self._get(key) is not None:
                return None
            self._values[key] = (str(value), time.monotonic() + ex if ex is not None else None)
            return True

    def delete(self, *keys: str) -> int:
        with self._lock:
            deleted = 0
            for key in keys:
                if self._get(key) is not None:
                    del self._values[key]
                    deleted += 1
            return deleted

    def ttl(self, key: str) -> int:
        with self._lock:
            value = self._get(key)
            if value is None:
                return -2
            return -1 if value[1] is None else max(0, int(value[1] - time.monotonic()))

    def incr(self, key: str) -> int:
        with self._lock:
            self._cleanup()
            value = self._get(key)
            count = int(value[0]) + 1 if value is not None else 1
            self._values[key] = (str(count), value[1] if value is not None else None)
            return count

    def expire(self, key: str, seconds: int) -> bool:
        with self._lock:
            value = self._get(key)
            if value is None:
                return False
            if seconds <= 0:
                del self._values[key]
            else:
                self._values[key] = (value[0], time.monotonic() + seconds)
            return True

    def pipeline(self) -> MemoryPipeline:
        return MemoryPipeline(self)


class MemoryPipeline:
    def __init__(self, cache: MemoryCache) -> None:
        self._cache = cache
        self._operations: list[tuple[str, str, int]] = []

    def incr(self, key: str) -> MemoryPipeline:
        self._operations.append(("incr", key, 0))
        return self

    def expire(self, key: str, seconds: int) -> MemoryPipeline:
        self._operations.append(("expire", key, seconds))
        return self

    def execute(self) -> list[int | bool]:
        operations, self._operations = self._operations, []
        with self._cache._lock:
            return [self._cache.incr(key) if operation == "incr" else self._cache.expire(key, seconds)
                    for operation, key, seconds in operations]
