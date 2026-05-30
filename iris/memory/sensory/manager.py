from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import threading
from typing import Any, Protocol

from loguru import logger

from iris.memory.models import ContentBlock, blocks_text, text_block
from iris.memory.sensory.readiness import ReadinessEvaluator


class SensoryMemoryProtocol(Protocol):
    """感覚記憶のインターフェース。

    なぜこの設計にしたか:
    将来的なマルチモーダル入力や別のバッファ機構に対応するため。
    """

    def set_flush_callback(self, callback: Callable[[str, list[ContentBlock]], None]) -> None: ...
    def set_readiness_evaluator(self, evaluator: ReadinessEvaluator) -> None: ...
    def add_fragment(self, content: str, is_final: bool) -> None: ...
    def add_fragment_block(self, block: ContentBlock, is_final: bool) -> None: ...
    def flush(self) -> None: ...
    def clear(self) -> None: ...
    def close(self) -> None: ...
    def store_raw(self, content: str, room_id: str = "") -> None: ...
    def store_raw_block(self, block: ContentBlock, room_id: str = "") -> None: ...
    def retrieve(self) -> dict[str, Any]: ...
    @property
    def has_pending_raw(self) -> bool: ...
    @property
    def fragment_count(self) -> int: ...
    @property
    def accumulated_blocks(self) -> list[ContentBlock]: ...


class SensoryMemoryManager:
    """感覚記憶 (Sensory Memory)。
    生の入力を処理前に一時保持する。

    2系統の入力を扱う:
    - 断片入力: add_fragment / add_fragment_block / timeout / flush 機構
    - 確定入力: store_raw / store_raw_block で完全な入力を保持 (main pipeline)

    脳科学対応: 感覚野 (sensory cortex) が raw な刺激を
    極短期間保持する処理に相当。
    """

    def __init__(
        self,
        timeout_ms: int = 800,
        max_fragments: int = 10,
        room_id: str = "",
    ):
        self._room_id = room_id
        self._timeout_ms = timeout_ms
        self._max_fragments = max_fragments
        self._fragments: list[ContentBlock] = []
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._flush_callback: Callable[[str, list[ContentBlock]], None] | None = None
        self._readiness: ReadinessEvaluator | None = None
        self._closed = False
        self._raw_input: ContentBlock | None = None

    # ---- fragment mode ----

    def set_flush_callback(self, callback: Callable[[str, list[ContentBlock]], None]) -> None:
        self._flush_callback = callback

    def set_readiness_evaluator(self, evaluator: ReadinessEvaluator) -> None:
        self._readiness = evaluator

    def add_fragment(self, content: str, is_final: bool) -> None:
        self.add_fragment_block(text_block(content), is_final)

    def add_fragment_block(self, block: ContentBlock, is_final: bool) -> None:
        if self._closed:
            return
        with self._lock:
            self._fragments.append(block)
            if len(self._fragments) >= self._max_fragments:
                self._flush_locked()
                return
            if is_final:
                self._flush_locked()
                return
            readiness = self._readiness
            if readiness is not None:
                text_frags = [b.get("text", "") for b in self._fragments if b.get("type") == "text"]
                if readiness.evaluate(text_frags, is_final=False):
                    self._flush_locked()
                    return
        self._reset_timer()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        self._cancel_timer_locked()
        if not self._fragments:
            return
        blocks = list(self._fragments)
        self._fragments.clear()
        if self._flush_callback:
            self._flush_callback("", blocks)

    def _reset_timer(self) -> None:
        with self._lock:
            self._cancel_timer_locked()
            if self._timeout_ms > 0:
                self._timer = threading.Timer(
                    self._timeout_ms / 1000,
                    self._on_timeout,
                )
                self._timer.daemon = True
                self._timer.start()

    def _cancel_timer_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _on_timeout(self) -> None:
        self.flush()

    def cancel(self) -> None:
        with self._lock:
            self._cancel_timer_locked()
            self._fragments.clear()

    def clear(self) -> None:
        with self._lock:
            self._cancel_timer_locked()
            self._fragments.clear()
            self._raw_input = None

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._cancel_timer_locked()
            self._fragments.clear()
            self._flush_callback = None

    # ---- raw input mode ----

    def store_raw(self, content: str, room_id: str = "") -> None:
        self.store_raw_block(text_block(content), room_id=room_id)

    def store_raw_block(self, block: ContentBlock, room_id: str = "") -> None:
        if room_id:
            self._room_id = room_id
        self._raw_input = block
        logger.debug("SensoryMemory: stored raw block type={}", block.get("type", "text"))

    def retrieve(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        with self._lock:
            if self._fragments:
                result["fragments"] = list(self._fragments)
                result["fragment"] = blocks_text(self._fragments)
        if self._raw_input is not None:
            result["raw"] = self._raw_input.get("text", "") if self._raw_input.get("type") == "text" else ""
            result["raw_block"] = self._raw_input
            result["raw_timestamp"] = datetime.now(UTC).isoformat()
        result["room_id"] = self._room_id
        return result

    @property
    def has_pending_raw(self) -> bool:
        return self._raw_input is not None

    @property
    def fragment_count(self) -> int:
        with self._lock:
            return len(self._fragments)

    @property
    def accumulated_blocks(self) -> list[ContentBlock]:
        with self._lock:
            return list(self._fragments)
