from __future__ import annotations

from loguru import logger

from iris.memory.models import ContentBlock, blocks_text
from iris.memory.short_term.extractor import EntityExtractor, RegexEntityExtractor
from iris.memory.short_term.models import MAX_CONTEXT_CHARS, ActiveUser, ShortTermSearchResult, ShortTermTurn
from iris.memory.short_term.presence import PresenceTracker
from iris.memory.short_term.protocol import ShortTermMemoryProtocol
from iris.memory.short_term.reference_tracker import ReferenceTracker
from iris.memory.short_term.renderer import render_short_term_context
from iris.memory.short_term.scorer import DefaultImportanceScorer, ImportanceScorer
from iris.memory.short_term.searcher import Searcher
from iris.memory.short_term.store import ShortTermStore
from iris.memory.short_term.topic_tracker import TopicTracker


class ShortTermMemoryManager(ShortTermMemoryProtocol):
    """短期記憶（ワーキングメモリ）の管理を行うFacade。

    直近の会話履歴（ターン数制限あり）、現在の話題、参照されたエンティティを保持する。
    内部で store / presence / searcher / topic_tracker / reference_tracker を構成する。
    """

    def __init__(
        self,
        max_turns: int = 30,
        max_topics: int = 5,
        *,
        importance_scorer: ImportanceScorer | None = None,
        entity_extractor: EntityExtractor | None = None,
    ) -> None:
        self._store = ShortTermStore(max_turns=max_turns, max_topics=max_topics)
        self._presence = PresenceTracker()
        self._searcher = Searcher(self._store)
        self._topic_tracker = TopicTracker(self._store)
        self._reference_tracker = ReferenceTracker(
            self._store,
            entity_extractor or RegexEntityExtractor(),
        )
        self._importance_scorer = importance_scorer or DefaultImportanceScorer()

    # ── Presence ──

    def add_user(self, account_id: str, display_name: str, room_id: str = "") -> None:
        self._presence.add_user(account_id, display_name, room_id=room_id)

    def remove_user(self, account_id: str, room_id: str = "") -> None:
        self._presence.remove_user(account_id, room_id=room_id)

    def get_active_users(self) -> list[ActiveUser]:
        return self._presence.get_active_users()

    def get_users_by_room(self, room_id: str) -> list[ActiveUser]:
        return self._presence.get_users_by_room(room_id)

    # ── Turn ──

    def add_turn(self, role: str, blocks: list[ContentBlock], account_id: str = "", room_id: str = "") -> None:
        if not blocks:
            return
        text = blocks_text(blocks)
        importance = self._importance_scorer.score(text)
        self._store.append_turn(role, blocks, text, importance, account_id=account_id, room_id=room_id)
        self._reference_tracker.extract_references(text)
        self._topic_tracker.extract_topics(text)
        logger.debug("ShortTerm: added {} turn, total={}", role, self._store.turn_count)

    # ── Search ──

    def search(
        self, query: str, max_results: int = 5, room_id: str = "", account_id: str = ""
    ) -> list[ShortTermSearchResult]:
        return self._searcher.search(query, max_results=max_results, room_id=room_id, account_id=account_id)

    def search_entities(self, entity_name: str) -> list[ShortTermTurn]:
        return self._searcher.search_entities(entity_name)

    # ── Context ──

    def render_context(
        self,
        max_chars: int = MAX_CONTEXT_CHARS,
        query: str | None = None,
        room_id: str = "",
        account_id: str = "",
    ) -> str:
        turns = self._store.scope_turns(room_id=room_id, account_id=account_id)
        relevant_results = (
            self._searcher.search(query, max_results=3, room_id=room_id, account_id=account_id) if query else None
        )
        return render_short_term_context(
            turns=turns,
            active_references=self._store.active_references,
            relevant_results=relevant_results,
            max_chars=max_chars,
            active_users=self._presence.get_active_users(),
            room_id=room_id,
        )

    # ── Turn queries ──

    def get_recent_turns(self, n: int = 4, room_id: str = "", account_id: str = "") -> list[ShortTermTurn]:
        return self._store.get_recent_turns(n=n, room_id=room_id, account_id=account_id)

    def get_unconsolidated_turns(self, room_id: str = "", account_id: str = "") -> list[ShortTermTurn]:
        return self._store.get_unconsolidated_turns(room_id=room_id, account_id=account_id)

    def mark_consolidated(self, room_id: str = "", account_id: str = "") -> None:
        self._store.mark_consolidated(room_id=room_id, account_id=account_id)

    def should_consolidate(self, room_id: str = "", account_id: str = "") -> bool:
        max_turns = self._store.max_turns
        threshold = max(3, max_turns // 2)
        if threshold > max_turns:
            threshold = max_turns
        return len(self._store.scope_turns(room_id=room_id, account_id=account_id)) >= threshold

    # ── Properties ──

    @property
    def current_topics(self) -> list[str]:
        return self._store.current_topics

    @property
    def turn_count(self) -> int:
        return self._store.turn_count

    # ── Lifecycle ──

    def clear(self) -> None:
        self._store.clear()
        self._presence.clear()
