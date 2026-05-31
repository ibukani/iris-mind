from __future__ import annotations

from contextlib import suppress
from typing import Any, Protocol


class MemoryManagerProtocol(Protocol):
    def set_sensory_buffer(self, buf: Any) -> None: ...
    def store(self, stream: str, data: Any, room_id: str = "", account_id: str = "") -> None: ...
    def retrieve(self, stream: str, room_id: str = "", account_id: str = "", **filters: Any) -> list[dict]: ...
    def search(
        self, query: str, stream: str | None = None, room_id: str = "", account_id: str = "", **kwargs: Any
    ) -> list[dict]: ...
    def clear(self, stream: str | None = None, room_id: str = "") -> None: ...
    def flush(self, room_id: str = "", account_id: str = "") -> None: ...
    def get_user_preferences(self, room_id: str = "", account_id: str = "") -> list[dict[str, Any]]: ...
    def add_episodic(
        self, content: str, kind: str = "", _metadata: dict | None = None, room_id: str = "", account_id: str = ""
    ) -> None: ...
    def get_recent(self, n: int = 3, room_id: str = "", account_id: str = "") -> list[dict[str, Any]]: ...
    def add_semantic(
        self, content: str, tags: list[str] | None = None, room_id: str = "", account_id: str = ""
    ) -> None: ...
    def add_semantic_by_type(
        self, entry_type: str, content: str, tags: list[str] | None = None, room_id: str = "", account_id: str = ""
    ) -> None: ...
    def search_semantic(
        self, query: str, max_results: int = 3, room_id: str = "", account_id: str = ""
    ) -> list[dict[str, Any]]: ...
    def search_emotional(
        self, current_emotion: Any | None = None, max_results: int = 5, room_id: str = ""
    ) -> list[dict[str, Any]]: ...

    short_term: Any
    long_term: Any
    goals: Any


def safe_count(store: Any | None) -> int:
    if store is None:
        return 0
    with suppress(Exception):
        return len(store.load_all())
    return 0
