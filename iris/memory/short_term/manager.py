from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Protocol

from loguru import logger

from iris.memory.models import ContentBlock, blocks_text
from iris.memory.short_term.extractor import EntityExtractor, RegexEntityExtractor
from iris.memory.short_term.models import MAX_CONTEXT_CHARS, MAX_TURN_LENGTH, SearchResult, TurnData
from iris.memory.short_term.renderer import render_short_term_context
from iris.memory.short_term.scorer import DefaultImportanceScorer, ImportanceScorer


def _truncate_blocks(blocks: list[ContentBlock], max_chars: int) -> list[ContentBlock]:
    total = 0
    result: list[ContentBlock] = []
    for b in blocks:
        txt = b.get("text", "")
        available = max_chars - total
        if available <= 0:
            break
        if not txt or len(txt) <= available:
            result.append(b)
            total += len(txt)
        else:
            tb: ContentBlock = {"type": b.get("type", "text")}
            tb["text"] = txt[:available]
            result.append(tb)
            total += available
    return result


class ShortTermMemoryProtocol(Protocol):
    """短期記憶マネージャーのインターフェース。

    なぜこの設計にしたか:
    他のレイヤーが具象クラスである ShortTermMemoryManager に直接依存するのを防ぎ、
    モック化やテスト用の代替実装を容易にするため。
    """

    def add_turn(self, role: str, blocks: list[ContentBlock], user_identity: str = "") -> None: ...
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...
    def search_entities(self, entity_name: str) -> list[TurnData]: ...
    def render_context(self, max_chars: int = MAX_CONTEXT_CHARS, query: str | None = None) -> str: ...
    def get_recent_turns(self, n: int = 4) -> list[TurnData]: ...
    def get_unconsolidated_turns(self) -> list[TurnData]: ...
    def mark_consolidated(self, up_to_index: int | None = None) -> None: ...
    def clear(self) -> None: ...
    def should_consolidate(self) -> bool: ...
    def add_user(self, user_id: str, nickname: str, session_id: str = "") -> None: ...
    def remove_user(self, user_id: str) -> None: ...
    def get_active_users(self) -> list[tuple[str, str]]: ...
    def get_users_by_session(self, session_id: str) -> list[tuple[str, str]]: ...
    @property
    def current_topics(self) -> list[str]: ...
    @property
    def turn_count(self) -> int: ...


class ShortTermMemoryManager:
    """短期記憶（ワーキングメモリ）の管理を行うクラス。

    直近の会話履歴（ターン数制限あり）、現在の話題、参照されたエンティティを保持する。
    """

    def __init__(
        self,
        max_turns: int = 30,
        max_topics: int = 5,
        *,
        importance_scorer: ImportanceScorer | None = None,
        entity_extractor: EntityExtractor | None = None,
    ) -> None:
        self._turns: list[TurnData] = []
        self._current_topics: list[str] = []
        self._active_references: set[str] = set()
        self._max_turns = max_turns
        self._max_topics = max_topics
        self._importance_scorer = importance_scorer or DefaultImportanceScorer()
        self._entity_extractor = entity_extractor or RegexEntityExtractor()
        self._active_users: dict[str, str] = {}
        self._session_users: dict[str, list[str]] = {}

    def add_user(self, user_id: str, nickname: str, session_id: str = "") -> None:
        self._active_users[user_id] = nickname
        if session_id:
            uid_list = self._session_users.setdefault(session_id, [])
            if user_id not in uid_list:
                uid_list.append(user_id)

    def remove_user(self, user_id: str) -> None:
        self._active_users.pop(user_id, None)
        for uid_list in self._session_users.values():
            if user_id in uid_list:
                uid_list.remove(user_id)
                break

    def get_active_users(self) -> list[tuple[str, str]]:
        return list(self._active_users.items())

    def get_users_by_session(self, session_id: str) -> list[tuple[str, str]]:
        uid_list = self._session_users.get(session_id, [])
        return [(uid, self._active_users.get(uid, uid)) for uid in uid_list if uid in self._active_users]

    def add_turn(self, role: str, blocks: list[ContentBlock], user_identity: str = "") -> None:
        if not blocks:
            return
        truncated_blocks = _truncate_blocks(blocks, MAX_TURN_LENGTH)
        text = blocks_text(truncated_blocks)
        entry: TurnData = {
            "role": role,
            "blocks": truncated_blocks,
            "timestamp": datetime.now(UTC).isoformat(),
            "consolidated": False,
            "importance": self._importance_scorer.score(text),
            "user_identity": user_identity,
        }
        self._turns.append(entry)
        if len(self._turns) > self._max_turns:
            self._turns.pop(0)
        self._extract_from_content(text)
        logger.debug("ShortTerm: added {} turn, total={}", role, len(self._turns))

    def _extract_from_content(self, content: str) -> None:
        """発話内容からエンティティの抽出と話題の更新を行う。"""
        for entity in self._entity_extractor.extract(content):
            self._active_references.add(entity)
        sentences = re.split(r"[。！？\.\!\?]", content)
        for s in sentences[:2]:
            s = s.strip()
            if len(s) > 5 and len(s) < 80 and s not in self._current_topics:
                self._current_topics.append(s)
        if len(self._current_topics) > self._max_topics:
            self._current_topics = self._current_topics[-self._max_topics :]

    def _turn_text(self, turn: TurnData) -> str:
        return blocks_text(turn.get("blocks", []))

    def _compute_relevance(self, query: str, turn: TurnData) -> float:
        if not query:
            return 0.0
        text = self._turn_text(turn)
        if not text:
            return 0.0
        q_words = set(re.findall(r"\w+", query.lower()))
        t_words = set(re.findall(r"\w+", text.lower()))
        if not q_words or not t_words:
            return 0.0
        overlap = len(q_words & t_words)
        return overlap / len(q_words)

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not query:
            return []

        scored: list[tuple[float, int, SearchResult]] = []
        for i, turn in enumerate(self._turns):
            relevance = self._compute_relevance(query, turn)
            text = self._turn_text(turn)
            if relevance == 0 and query.lower() not in text.lower():
                continue

            actual_relevance = relevance if relevance > 0 else 0.01
            turn_copy: SearchResult = {**turn, "relevance": actual_relevance, "index": i}
            scored.append((actual_relevance, turn.get("importance", 0), turn_copy))

        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [s[2] for s in scored[:max_results]]

    def search_entities(self, entity_name: str) -> list[TurnData]:
        entity_lower = entity_name.lower().strip()
        results: list[TurnData] = [turn for turn in self._turns if entity_lower in self._turn_text(turn).lower()]
        return results[-5:]

    def render_context(self, max_chars: int = MAX_CONTEXT_CHARS, query: str | None = None) -> str:
        return render_short_term_context(
            turns=self._turns,
            active_references=self._active_references,
            search_fn=self.search,
            max_chars=max_chars,
            query=query,
            active_users=self.get_active_users(),
        )

    def get_recent_turns(self, n: int = 4) -> list[TurnData]:
        """直近のNターンを取得する。"""
        return self._turns[-n:]

    def get_unconsolidated_turns(self) -> list[TurnData]:
        """まだ圧縮（長期記憶化）されていないターンの一覧を取得する。"""
        return [t for t in self._turns if not t.get("consolidated")]

    def mark_consolidated(self, up_to_index: int | None = None) -> None:
        """指定されたインデックス（または全て）のターンを圧縮済みにマークする。"""
        if up_to_index is None:
            for t in self._turns:
                t["consolidated"] = True
        else:
            for t in self._turns[:up_to_index]:
                t["consolidated"] = True

    def clear(self) -> None:
        """短期記憶のすべての状態をクリアする。"""
        self._turns.clear()
        self._current_topics.clear()
        self._active_references.clear()
        self._active_users.clear()
        self._session_users.clear()

    def should_consolidate(self) -> bool:
        """メモリの圧縮（要約化）が必要かどうかを判定する。

        ターン数が上限（max_turns）の半分、または3ターン以上のいずれか大きい方に達した場合にTrueを返す。
        ただし、max_turns自体が小さい場合はmax_turnsを超えないように閾値を調整する。
        """
        threshold = max(3, self._max_turns // 2)
        if threshold > self._max_turns:
            threshold = self._max_turns
        return len(self._turns) >= threshold

    @property
    def current_topics(self) -> list[str]:
        """現在の話題の一覧を取得する。"""
        return list(self._current_topics)

    @property
    def turn_count(self) -> int:
        """現在のターン数を取得する。"""
        return len(self._turns)
