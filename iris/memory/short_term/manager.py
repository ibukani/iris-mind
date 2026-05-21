from __future__ import annotations

from datetime import UTC, datetime
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_MAX_TURN_LENGTH = 500
_MAX_CONTEXT_CHARS = 600


class ShortTermMemoryManager:
    """短期記憶（ワーキングメモリ）の管理を行うクラス。

    直近の会話履歴（ターン数制限あり）、現在の話題、参照されたエンティティを保持する。
    """

    def __init__(self, max_turns: int = 10, max_topics: int = 5) -> None:
        self._turns: list[dict[str, Any]] = []
        self._current_topics: list[str] = []
        self._active_references: set[str] = set()
        self._max_turns = max_turns
        self._max_topics = max_topics

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
            "importance": self._compute_importance(truncated),
        }
        self._turns.append(entry)
        if len(self._turns) > self._max_turns:
            self._turns.pop(0)
        self._extract_from_content(truncated)
        logger.debug("ShortTerm: added %s turn, total=%d", role, len(self._turns))

    def _compute_importance(self, content: str) -> int:
        """発話内容から重要度（0〜5）を算出する。

        特定のキーワードの有無や感嘆符の数、大文字の連続などを判定材料とする。
        """
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

    def _extract_from_content(self, content: str) -> None:
        """発話内容からエンティティの抽出と話題の更新を行う。"""
        for entity in self._extract_entities(content):
            self._active_references.add(entity)
        sentences = re.split(r"[。！？\.\!\?]", content)
        for s in sentences[:2]:
            s = s.strip()
            if len(s) > 5 and len(s) < 80 and s not in self._current_topics:
                self._current_topics.append(s)
        if len(self._current_topics) > self._max_topics:
            self._current_topics = self._current_topics[-self._max_topics :]

    def _extract_entities(self, content: str) -> list[str]:
        """発話内からURL、ファイルパス、ハッシュタグ、メンション、引用句などのエンティティを抽出する。"""
        entities: list[str] = []
        entities.extend(re.findall(r"https?://[^\s]+", content))
        entities.extend(re.findall(r"(?:/[^\s/]+)+(?:/?)", content))
        entities.extend(re.findall(r"#\w+", content))
        entities.extend(re.findall(r"@\w+", content))
        entities.extend(re.findall(r"「([^」]+)」", content))
        entities.extend(re.findall(r'"([^"]{3,})"', content))
        entities.extend(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b", content))
        return list({e for e in entities if len(e) > 2})

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
        scored: list[tuple[float, int, dict[str, Any]]] = []
        for i, turn in enumerate(self._turns):
            relevance = self._compute_relevance(query, turn)
            if relevance > 0 or (query and query.lower() in turn.get("content", "").lower()):
                if relevance == 0:
                    relevance = 0.01
                scored.append((relevance, turn.get("importance", 0), dict(turn)))
                scored[-1][2]["relevance"] = relevance
                scored[-1][2]["index"] = i
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
            shown_indices: set[int] = set()
            for r in relevant:
                shown_indices.add(r.get("index", -1))
                label = "User" if r["role"] == "user" else "Iris"
                parts.append(f"- {label}: 「{r['content'][:100]}」(関連度 {r.get('relevance', 0):.2f})")
            for t in reversed(self._turns[-4:]):
                idx = self._turns.index(t)
                if idx in shown_indices:
                    continue
                shown_indices.add(idx)
                label = "User" if t["role"] == "user" else "Iris"
                parts.append(f"- {label}: 「{t['content'][:100]}」")

        if self._current_topics:
            parts.append("### 現在の話題")
            parts.extend(f"- {topic}" for topic in self._current_topics[-3:])
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
