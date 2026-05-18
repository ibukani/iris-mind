from __future__ import annotations

import logging
import math
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.limbic.models import EmotionState

from iris.event.event_types import InputReady, InputReceived, TimerTick
from iris.memory.sensory.buffer import InputBuffer
from iris.memory.short_term_memory import ShortTermMemory
from iris.memory.stores import EpisodicStore, SemanticStore
from iris.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)


class MemoryManager:
    """記憶マネージャー。

    脳科学に基づく3層構造:
    - SensoryMemory (感覚記憶): InputBuffer による raw 入力の一時保持
    - ShortTermMemory (短期記憶): 処理中の情報（ワーキングメモリ）
    - LongTermMemory (長期記憶): EpisodicStore + SemanticStore による永続記憶
    """

    def __init__(
        self,
        *,
        event_bus: Any = None,
        episodic: EpisodicStore | None = None,
        semantic: SemanticStore | None = None,
        vector_store: VectorStore | None = None,
        short_term: ShortTermMemory | None = None,
        proactive_config: Any = None,
    ) -> None:
        # === 感覚記憶 (Sensory Memory) ===
        self._sensory_buffer: InputBuffer | None = None

        # === 短期記憶 (Short-Term Memory / Working Memory) ===
        self._short_term: ShortTermMemory = short_term or ShortTermMemory()

        # === 長期記憶 (Long-Term Memory) ===
        self._episodic = episodic
        self._semantic = semantic
        self._vector_store = vector_store

        self._event_bus = event_bus
        self._proactive_config = proactive_config
        self._pending_input: dict[str, str] = {}
        self._pending_lock: threading.Lock = threading.Lock()

        if event_bus is not None:
            event_bus.subscribe("InputReceived", self._on_input_received)
            event_bus.subscribe("TimerTick", self._on_timer_tick)

    def set_sensory_buffer(self, buf: InputBuffer) -> None:
        self._sensory_buffer = buf

    def _on_input_received(self, event: InputReceived) -> None:
        if not event.content:
            return
        with self._pending_lock:
            self._pending_input[event.session_id] = event.content
        logger.debug(
            "MemoryManager: input pending session=%s content=%.80s",
            event.session_id,
            event.content,
        )

    def _on_timer_tick(self, event: TimerTick) -> None:
        session_id = ""
        content = ""
        with self._pending_lock:
            if self._pending_input:
                session_id, content = self._pending_input.popitem()

        if content and session_id:
            self._event_bus.publish(
                InputReady(
                    timestamp=None,
                    source="memory",
                    session_id=session_id,
                    content=content,
                    context={},
                )
            )
            return

        if self._proactive_config is not None:
            self._event_bus.publish(
                InputReady(
                    timestamp=None,
                    source="memory",
                    session_id="",
                    content="",
                    context={"from_timer": True},
                )
            )

    def store(self, stream: str, data: Any) -> None:
        if stream == "sensory" and self._sensory_buffer:
            if isinstance(data, str):
                self._sensory_buffer.add_fragment(data, is_final=True)
            elif isinstance(data, dict) and "text" in data:
                self._sensory_buffer.add_fragment(data["text"], is_final=True)

        elif stream == "short_term":
            if isinstance(data, str):
                self._short_term.add(data)
            elif isinstance(data, dict):
                self._short_term.add(
                    data.get("content") or data.get("summary") or str(data),
                    metadata=data.get("metadata"),
                )

        elif stream == "episodic" and self._episodic:
            summary = ""
            kind = ""
            if isinstance(data, str):
                summary = data
            elif isinstance(data, dict):
                summary = data.get("content") or data.get("summary") or str(data)
                kind = data.get("kind", "")

            if kind:
                summary = f"[{kind}] {summary}"
            self._episodic.add(summary)
            self._short_term.add(summary, metadata={"type": "episodic", "kind": kind})

        elif stream == "semantic" and self._semantic:
            self._semantic.add(data)
            content = data.get("content") if isinstance(data, dict) else str(data)
            self._short_term.add(content, metadata={"type": "semantic"})

        else:
            logger.warning("MemoryManager: unknown stream=%s", stream)

    def retrieve(self, stream: str, **filters: Any) -> list[dict]:
        if stream == "sensory" and self._sensory_buffer:
            return [{"text": self._sensory_buffer.accumulated_text}]

        if stream == "short_term":
            n = filters.get("n", 5)
            if not isinstance(n, int):
                n = 5
            return self._short_term.get_recent(n)

        if stream == "episodic" and self._episodic:
            n = filters.get("n", 5)
            if not isinstance(n, int):
                n = 5
            return self._episodic.get_recent(n)

        return []

    def search(self, query: str, stream: str | None = None, **kwargs: Any) -> list[dict]:
        max_results = kwargs.get("max_results", 3)
        if not isinstance(max_results, int):
            max_results = 3

        if (stream == "semantic" or (stream is None and self._semantic)) and self._semantic is not None:
            results = self._semantic.search(query=query, max_results=max_results)
            return [
                {
                    "content": r.get("content", ""),
                    "tags": r.get("tags", []),
                    "type": r.get("type", "unknown"),
                    "score": round(r.get("score", 0.0), 4),
                    "timestamp": r.get("timestamp", ""),
                }
                for r in results
            ]
        if self._vector_store:
            results = self._vector_store.search(query=query, max_results=max_results)
            return [
                {
                    "content": r.get("content", ""),
                    "tags": r.get("tags", []),
                    "type": r.get("type", "unknown"),
                    "score": round(r.get("score", 0.0), 4),
                    "timestamp": r.get("timestamp", ""),
                }
                for r in results
            ]
        return []

    def clear(self, stream: str | None = None) -> None:
        if stream == "sensory" and self._sensory_buffer:
            self._sensory_buffer.close()

        if stream == "short_term" or stream is None:
            self._short_term.clear()

        if (stream == "episodic" or stream is None) and self._episodic:
            self._episodic.clear()

        if (stream == "semantic" or stream is None) and self._semantic:
            self._semantic.clear()

    # === Backward compat API (for LLMPipeline) ===

    def get_user_preferences(self) -> list[dict[str, Any]]:
        return self.search("ユーザーの好み 興味 趣味", stream="semantic", max_results=2)

    def add_episodic(self, content: str, kind: str = "", _metadata: dict | None = None) -> None:
        self.store("episodic", {"content": content, "kind": kind})

    def get_recent(self, n: int = 3) -> list[dict[str, Any]]:
        return self.retrieve("episodic", n=n)

    def add_semantic(self, content: str, tags: list[str] | None = None) -> None:
        self.store("semantic", {"content": content, "tags": tags or []})

    def add_semantic_by_type(self, entry_type: str, content: str, tags: list[str] | None = None) -> None:
        self.store("semantic", {"content": content, "type": entry_type, "tags": tags or []})

    def search_semantic(self, query: str, max_results: int = 3) -> list[dict[str, Any]]:
        return self.search(query, stream="semantic", max_results=max_results)

    def search_emotional(
        self,
        current_emotion: EmotionState | None = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """感情タグが付いたエピソード記憶を取得（感情強度順）。

        現在の感情状態が指定された場合は感情類似度で再ランクする。
        """
        if not self._episodic:
            return []

        all_entries = self._episodic.get_recent(self._episodic.max_entries)
        emotion_entries = [e for e in all_entries if e.get("metadata", {}).get("type") == "emotion_tag"]

        if not emotion_entries:
            return []

        if current_emotion is not None:
            scored: list[tuple[float, dict]] = []
            for e in emotion_entries:
                meta = e.get("metadata", {})
                meta_emotion = meta.get("emotion", {})
                distance = _pad_distance(current_emotion, meta_emotion)
                intensity = meta.get("intensity", 0)
                score = intensity / max(distance, 0.01)
                scored.append((score, e))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [e for _, e in scored[:max_results]]

        return sorted(
            emotion_entries,
            key=lambda e: e.get("metadata", {}).get("intensity", 0),
            reverse=True,
        )[:max_results]


def _pad_distance(
    a: EmotionState,
    b: Mapping[str, Any],
) -> float:
    a_val = a.valence
    a_aro = a.arousal
    a_dom = a.dominance
    b_val = float(b.get("valence", 0))
    b_aro = float(b.get("arousal", 0))
    b_dom = float(b.get("dominance", 0))
    return math.sqrt((a_val - b_val) ** 2 + (a_aro - b_aro) ** 2 + (a_dom - b_dom) ** 2)
