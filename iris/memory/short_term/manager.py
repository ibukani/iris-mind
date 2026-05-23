from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Protocol

from loguru import logger

_MAX_TURN_LENGTH = 500
_MAX_CONTEXT_CHARS = 600


class ImportanceScorer(Protocol):
    """発話内容から重要度を算出するインターフェース。

    なぜこの設計にしたか:
    将来的にLLMを用いた重要度判定や、異なるヒューリスティックルールを容易に差し替え可能にするため。
    """

    def score(self, content: str) -> int: ...


class DefaultImportanceScorer:
    """ヒューリスティックに基づくデフォルトの重要度判定器。"""

    def score(self, content: str) -> int:
        score = 0
        lower = content.lower()
        if any(w in lower for w in ["important", "大事", "覚えて", "remember", "注意", "critical", "urgent"]):
            score += 3
        if any(w in lower for w in ["please", "お願い", "help", "assist", "question", "質問"]):
            score += 1
        if re.search(r"[A-Z]{3,}", content):
            score += 1
        if content.count("!") >= 2:
            score += 1
        return min(score, 5)


class EntityExtractor(Protocol):
    """テキストから特定の参照エンティティを抽出するインターフェース。

    なぜこの設計にしたか:
    正規表現による抽出だけでなく、NERモデルや外部NLPライブラリを用いた抽出エンジンへの差し替えをサポートするため。
    """

    def extract(self, content: str) -> list[str]: ...


class RegexEntityExtractor:
    """正規表現に基づくデフォルトのエンティティ抽出器。"""

    def extract(self, content: str) -> list[str]:
        entities: list[str] = []
        entities.extend(re.findall(r"https?://[^\s]+", content))
        entities.extend(re.findall(r"(?:/[^\s/]+)+(?:/?)", content))
        entities.extend(re.findall(r"#\w+", content))
        entities.extend(re.findall(r"@\w+", content))
        entities.extend(re.findall(r"「([^」]+)」", content))
        entities.extend(re.findall(r'"([^"]{3,})"', content))
        entities.extend(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b", content))
        return list({e for e in entities if len(e) > 2})


class ShortTermMemoryProtocol(Protocol):
    """短期記憶マネージャーのインターフェース。

    なぜこの設計にしたか:
    他のレイヤーが具象クラスである ShortTermMemoryManager に直接依存するのを防ぎ、
    モック化やテスト用の代替実装を容易にするため。
    """

    def add_turn(self, role: str, content: str) -> None: ...
    def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]: ...
    def search_entities(self, entity_name: str) -> list[dict[str, Any]]: ...
    def render_context(self, max_chars: int = _MAX_CONTEXT_CHARS, query: str | None = None) -> str: ...
    def get_recent_turns(self, n: int = 4) -> list[dict[str, Any]]: ...
    def get_unconsolidated_turns(self) -> list[dict[str, Any]]: ...
    def mark_consolidated(self, up_to_index: int | None = None) -> None: ...
    def clear(self) -> None: ...
    def should_consolidate(self) -> bool: ...
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
        max_turns: int = 10,
        max_topics: int = 5,
        *,
        importance_scorer: ImportanceScorer | None = None,
        entity_extractor: EntityExtractor | None = None,
    ) -> None:
        self._turns: list[dict[str, Any]] = []
        self._current_topics: list[str] = []
        self._active_references: set[str] = set()
        self._max_turns = max_turns
        self._max_topics = max_topics
        self._importance_scorer = importance_scorer or DefaultImportanceScorer()
        self._entity_extractor = entity_extractor or RegexEntityExtractor()

    def add_turn(self, role: str, content: str) -> None:
        """会話の1ターンを追加し、エンティティの抽出と話題の更新を行う。

        Args:
            role: 発話者のロール（"user" または "assistant"）
            content: 発話内容
        """
        if not content:
            return
        truncated = content[:_MAX_TURN_LENGTH]
        entry: dict[str, Any] = {
            "role": role,
            "content": truncated,
            "timestamp": datetime.now(UTC).isoformat(),
            "consolidated": False,
            "importance": self._importance_scorer.score(truncated),
        }
        self._turns.append(entry)
        if len(self._turns) > self._max_turns:
            self._turns.pop(0)
        self._extract_from_content(truncated)
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

    def _compute_relevance(self, query: str, turn: dict[str, Any]) -> float:
        """クエリと会話ターンの関連度スコアを算出する。"""
        if not query or not turn.get("content"):
            return 0.0
        q_words = set(re.findall(r"\w+", query.lower()))
        t_words = set(re.findall(r"\w+", turn["content"].lower()))
        if not q_words or not t_words:
            return 0.0
        overlap = len(q_words & t_words)
        return overlap / len(q_words)

    def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """クエリに関連する会話ターンを検索する。"""
        if not query:
            return []

        scored: list[tuple[float, int, dict[str, Any]]] = []
        for i, turn in enumerate(self._turns):
            relevance = self._compute_relevance(query, turn)
            content = turn.get("content", "")
            if relevance == 0 and query.lower() not in content.lower():
                continue

            actual_relevance = relevance if relevance > 0 else 0.01
            turn_copy = dict(turn)
            turn_copy["relevance"] = actual_relevance
            turn_copy["index"] = i

            scored.append((actual_relevance, turn.get("importance", 0), turn_copy))

        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [s[2] for s in scored[:max_results]]

    def search_entities(self, entity_name: str) -> list[dict[str, Any]]:
        """エンティティ名が含まれる会話ターンを検索する。"""
        entity_lower = entity_name.lower().strip()
        results: list[dict[str, Any]] = []
        for i, turn in enumerate(self._turns):
            if entity_lower in turn.get("content", "").lower():
                turn_copy = dict(turn)
                turn_copy["index"] = i
                results.append(turn_copy)
        return results[-5:]

    def render_context(self, max_chars: int = _MAX_CONTEXT_CHARS, query: str | None = None) -> str:
        """短期記憶の内容をプロンプト注入用のテキストフォーマットに整形する。"""
        if not self._turns:
            return ""
        parts: list[str] = []

        if query:
            parts.append("### 直近の会話（関連）")
            relevant = self.search(query, max_results=3)
            shown_indices = {r.get("index", -1) for r in relevant}
            for r in relevant:
                role = r.get("role", "system")
                label = "User" if role == "user" else "Iris"
                prefix = "(思考) " if role == "thought" else ""
                parts.append(f"- {label}: {prefix}「{r['content'][:100]}」(関連度 {r.get('relevance', 0):.2f})")
            for t in reversed(self._turns[-4:]):
                idx = self._turns.index(t)
                if idx in shown_indices:
                    continue
                shown_indices.add(idx)
                role = t.get("role", "system")
                label = "User" if role == "user" else "Iris"
                prefix = "(思考) " if role == "thought" else ""
                parts.append(f"- {label}: {prefix}「{t['content'][:100]}」")

        if self._active_references:
            refs = sorted(self._active_references, key=len, reverse=True)[:5]
            parts.append("### 参照エンティティ")
            parts.append(", ".join(refs))

        if not parts:
            return ""
        text = "\n".join(parts)
        if len(text) > max_chars:
            text = text[: max_chars - 3] + "..."
        return text

    def get_recent_turns(self, n: int = 4) -> list[dict[str, Any]]:
        """直近のNターンを取得する。"""
        return self._turns[-n:]

    def get_unconsolidated_turns(self) -> list[dict[str, Any]]:
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
