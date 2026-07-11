from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Generic, TypeVar


K = TypeVar("K")
V = TypeVar("V")


class TTLBoundedCache(Generic[K, V]):
    def __init__(self, *, max_entries: int, ttl_seconds: float) -> None:
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = max(0.1, float(ttl_seconds))
        self._items: OrderedDict[K, tuple[float, V]] = OrderedDict()

    def get(self, key: K) -> V | None:
        item = self._items.get(key)
        if item is None:
            return None
        created_at, value = item
        if time.monotonic() - created_at > self.ttl_seconds:
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return value

    def set(self, key: K, value: V) -> V:
        self._items[key] = (time.monotonic(), value)
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)
        return value

    def get_or_set(self, key: K, factory: Callable[[], V]) -> V:
        value = self.get(key)
        if value is not None:
            return value
        return self.set(key, factory())

    def clear(self) -> None:
        self._items.clear()
