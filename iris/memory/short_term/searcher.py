from __future__ import annotations

import re
from typing import TYPE_CHECKING

from iris.memory.short_term.models import ShortTermScope, ShortTermSearchResult, ShortTermTurn

if TYPE_CHECKING:
    from iris.memory.short_term.store import ShortTermStore


class Searcher:
    """関連度検索・entity検索。"""

    def __init__(self, store: ShortTermStore) -> None:
        self._store = store

    def _compute_relevance(self, query: str, turn: ShortTermTurn) -> float:
        if not query:
            return 0.0
        text = self._store.turn_text(turn)
        if not text:
            return 0.0
        q_words = set(re.findall(r"\w+", query.lower()))
        t_words = set(re.findall(r"\w+", text.lower()))
        if not q_words or not t_words:
            return 0.0
        overlap = len(q_words & t_words)
        return overlap / len(q_words)

    def search(
        self,
        query: str,
        max_results: int = 5,
        room_id: str = "",
        account_id: str = "",
    ) -> list[ShortTermSearchResult]:
        if not query:
            return []

        turns = self._store.scope_turns(room_id=room_id, account_id=account_id)

        scored: list[tuple[float, int, int, ShortTermSearchResult]] = []
        for orig_idx, turn in enumerate(turns):
            relevance = self._compute_relevance(query, turn)
            text = self._store.turn_text(turn)
            if relevance == 0 and query.lower() not in text.lower():
                continue

            actual_relevance = relevance if relevance > 0 else 0.01
            result = ShortTermSearchResult.from_turn(
                turn,
                relevance=actual_relevance,
                index=orig_idx,
            )
            scored.append((actual_relevance, turn.importance, -orig_idx, result))

        scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
        return [s[3] for s in scored[:max_results]]

    def search_entities(self, entity_name: str) -> list[ShortTermTurn]:
        entity_lower = entity_name.lower().strip()
        results: list[ShortTermTurn] = [
            turn for turn in self._store.turns if entity_lower in self._store.turn_text(turn).lower()
        ]
        return results[-5:]


__all__ = ["Searcher", "ShortTermScope"]
