from __future__ import annotations

from collections.abc import Callable
import threading

from iris.memory.models import ContentBlock, text_block
from iris.memory.sensory.readiness import ReadinessEvaluator
from iris.memory.sensory.store import SensoryStore


class SensoryMemoryAssembler:
    """断片入力 (fragment mode) のタイマー制御・readiness判定を伴うフラッシュ処理を担当するクラス。

    状態（fragmentsリスト）は SensoryStore が保持し、自身は制御フローのみを処理する。
    """

    def __init__(
        self,
        store: SensoryStore,
        timeout_ms: int = 800,
        max_fragments: int = 10,
    ) -> None:
        self._store = store
        self._timeout_ms = timeout_ms
        self._max_fragments = max_fragments
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.RLock()
        self._flush_callback: Callable[[str, list[ContentBlock]], None] | None = None
        self._readiness: ReadinessEvaluator | None = None
        self._closed = False

    def set_flush_callback(self, callback: Callable[[str, list[ContentBlock]], None]) -> None:
        with self._lock:
            self._flush_callback = callback

    def set_readiness_evaluator(self, evaluator: ReadinessEvaluator) -> None:
        with self._lock:
            self._readiness = evaluator

    def add_fragment(self, content: str, is_final: bool, room_id: str = "") -> None:
        self.add_fragment_block(text_block(content), is_final, room_id)

    def add_fragment_block(self, block: ContentBlock, is_final: bool, room_id: str = "") -> None:
        if self._closed:
            return
        with self._lock:
            self._store.add_fragment(block, room_id)
            snapshot = self._store.retrieve(room_id)
            fragment_count = len(snapshot.fragments)

            if fragment_count >= self._max_fragments:
                self._flush_locked(room_id)
                return
            if is_final:
                self._flush_locked(room_id)
                return
            readiness = self._readiness
            if readiness is not None:
                text_frags = [b.get("text", "") for b in snapshot.fragments if b.get("type") == "text"]
                if readiness.evaluate(text_frags, is_final=False):
                    self._flush_locked(room_id)
                    return
            self._reset_timer_locked(room_id)

    def flush(self, room_id: str = "") -> None:
        with self._lock:
            self._flush_locked(room_id)

    def _flush_locked(self, room_id: str = "") -> None:
        self._cancel_timer_locked(room_id)
        blocks = self._store.take_fragments(room_id)
        if not blocks:
            return
        if self._flush_callback:
            self._flush_callback(room_id, blocks)

    def _reset_timer_locked(self, room_id: str = "") -> None:
        self._cancel_timer_locked(room_id)
        if self._closed or self._timeout_ms <= 0:
            return
        self._timers[room_id] = threading.Timer(
            self._timeout_ms / 1000,
            self._on_timeout,
            args=[room_id],
        )
        self._timers[room_id].daemon = True
        self._timers[room_id].start()

    def _cancel_timer_locked(self, room_id: str = "") -> None:
        timer = self._timers.pop(room_id, None)
        if timer is not None:
            timer.cancel()

    def _on_timeout(self, room_id: str = "") -> None:
        self.flush(room_id)

    def cancel(self, room_id: str | None = None) -> None:
        with self._lock:
            if room_id is not None:
                self._cancel_timer_locked(room_id)
                self._store.take_fragments(room_id)
            else:
                for r_id in list(self._timers.keys()):
                    self._cancel_timer_locked(r_id)
                    self._store.take_fragments(r_id)

    def clear(self, room_id: str | None = None) -> None:
        with self._lock:
            if room_id is not None:
                self._cancel_timer_locked(room_id)
                self._store.take_fragments(room_id)
            else:
                for r_id in list(self._timers.keys()):
                    self._cancel_timer_locked(r_id)
                    self._store.take_fragments(r_id)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for r_id in list(self._timers.keys()):
                self._cancel_timer_locked(r_id)
                self._store.take_fragments(r_id)
            self._flush_callback = None

    def fragment_count(self, room_id: str = "") -> int:
        return len(self._store.retrieve(room_id).fragments)

    def accumulated_blocks(self, room_id: str = "") -> list[ContentBlock]:
        return self._store.retrieve(room_id).fragments
