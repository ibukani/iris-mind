from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from iris.event.event_types import DebugSnapshotEvent, Event


class EventTracer:
    def __init__(self, max_entries: int = 500) -> None:
        self._buffer: list[dict[str, Any]] = []
        self._max_entries = max_entries
        self._enabled = True
        self._publish_count = 0
        self._error_count = 0
        self._subscriber_count = 0
        self._category_index: dict[str, list[int]] = defaultdict(list)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def publish_count(self) -> int:
        return self._publish_count

    @property
    def subscriber_count(self) -> int:
        return self._subscriber_count

    @property
    def error_count(self) -> int:
        return self._error_count

    def on_event(self, event: Event) -> None:
        if not self._enabled:
            return
        self._publish_count += 1
        entry: dict[str, Any] = {
            "timestamp": (event.timestamp or datetime.now()).isoformat(timespec="seconds"),
            "source": event.source,
            "trace_id": event.trace_id,
            "type": type(event).__name__,
        }
        if isinstance(event, DebugSnapshotEvent):
            entry["category"] = event.category
            entry["data"] = event.data
            entry["trigger"] = event.trigger
            idx = len(self._buffer)
            self._category_index[event.category].append(idx)
        entry["raw"] = event.to_dict()
        self._buffer.append(entry)
        if len(self._buffer) > self._max_entries:
            self._buffer.pop(0)
            for cat, indices in list(self._category_index.items()):
                self._category_index[cat] = [i - 1 for i in indices if i > 0]
                if not self._category_index[cat]:
                    del self._category_index[cat]

    def recent(self, n: int = 10, type_filter: str | None = None) -> list[dict[str, Any]]:
        results = self._buffer
        if type_filter:
            results = [e for e in results if e["type"] == type_filter]
        return results[-n:]

    def find(
        self,
        category: str | None = None,
        type_filter: str | None = None,
        n: int = 10,
    ) -> list[dict[str, Any]]:
        results = self._buffer
        if category:
            indices = self._category_index.get(category, [])
            results = [self._buffer[i] for i in indices if i < len(self._buffer)]
        if type_filter:
            results = [e for e in results if e["type"] == type_filter]
        return results[-n:]

    def by_trace_id(self, trace_id: str) -> list[dict[str, Any]]:
        return [e for e in self._buffer if e["trace_id"] == trace_id]
