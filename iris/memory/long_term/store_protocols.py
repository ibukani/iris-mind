from __future__ import annotations

from typing import Protocol, runtime_checkable

from iris.memory.long_term.models import EpisodicEntry, SemanticEntry


class AgentsMdStoreProtocol(Protocol):
    def load(self) -> str: ...
    def update(self, new_content: str) -> None: ...


@runtime_checkable
class EpisodicStoreProtocol(Protocol):
    @property
    def max_entries(self) -> int: ...
    def add(
        self,
        summary: str,
        metadata: dict | None = None,
        room_id: str = "",
        account_id: str = "",
    ) -> EpisodicEntry | None: ...
    def get_recent(self, n: int = 5, room_id: str = "", account_id: str = "") -> list[dict]: ...
    def clear(self) -> None: ...
    def load_all(self) -> list[dict]: ...


@runtime_checkable
class SemanticStoreProtocol(Protocol):
    def add(
        self,
        entry: dict,
        room_id: str = "",
        account_id: str = "",
    ) -> SemanticEntry | None: ...
    def search(self, query: str, max_results: int = 3, account_id: str = "") -> list[dict]: ...
    def clear(self) -> None: ...
    def load_all(self) -> list[dict]: ...
