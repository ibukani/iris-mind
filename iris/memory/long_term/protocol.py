from __future__ import annotations

from typing import Any, Protocol

from iris.memory.long_term.models import (
    EpisodicEntry,
    EpisodicScope,
    SearchHit,
    SemanticEntry,
    SemanticScope,
)
from iris.memory.long_term.store_protocols import EpisodicStoreProtocol, SemanticStoreProtocol


class LongTermMemoryProtocol(Protocol):
    @property
    def episodic(self) -> EpisodicStoreProtocol | None: ...

    @property
    def semantic(self) -> SemanticStoreProtocol | None: ...

    def store_episodic(self, data: Any, kind: str = "", room_id: str = "", account_id: str = "") -> None: ...
    def get_episodic_recent(self, n: int = 5, room_id: str = "", account_id: str = "") -> list[dict[str, Any]]: ...
    def get_episodic_scope(self, scope: EpisodicScope) -> list[dict[str, Any]]: ...
    def clear_episodic(self) -> None: ...
    def store_semantic(self, data: Any, room_id: str = "", account_id: str = "") -> None: ...
    def search_semantic(
        self, query: str, max_results: int = 3, room_id: str = "", account_id: str = ""
    ) -> list[dict[str, Any]]: ...
    def search_semantic_typed(
        self, query: str, max_results: int = 3, scope: SemanticScope | None = None
    ) -> list[SearchHit]: ...
    def clear_semantic(self) -> None: ...
    def search_vector(self, query: str, max_results: int = 3) -> list[dict[str, Any]]: ...
    def search_vector_typed(self, query: str, max_results: int = 3) -> list[SearchHit]: ...
    def search_emotional(
        self,
        current_emotion: Any | None = None,
        max_results: int = 5,
        room_id: str = "",
    ) -> list[dict[str, Any]]: ...


__all__ = [
    "EpisodicEntry",
    "EpisodicScope",
    "LongTermMemoryProtocol",
    "SearchHit",
    "SemanticEntry",
    "SemanticScope",
]
