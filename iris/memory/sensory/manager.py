from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import threading
from typing import Protocol

from loguru import logger

from iris.memory.sensory.readiness import ReadinessEvaluator


class SensoryMemoryProtocol(Protocol):
    """感覚記憶のインターフェース。

    なぜこの設計にしたか:
    将来的なマルチモーダル入力や別のバッファ機構に対応するため。
    """

    def set_flush_callback(self, callback: Callable[[str, str], None]) -> None: ...
    def set_readiness_evaluator(self, evaluator: ReadinessEvaluator) -> None: ...
    def add_fragment(self, content: str, is_final: bool) -> None: ...
    def flush(self) -> None: ...
    def clear(self) -> None: ...
    def close(self) -> None: ...
    def store_raw(self, content: str) -> None: ...
    def retrieve(self) -> dict[str, str]: ...
    @property
    def has_pending_raw(self) -> bool: ...
    @property
    def last_raw_input(self) -> str: ...
    @property
    def fragment_count(self) -> int: ...
    @property
    def accumulated_text(self) -> str: ...


class SensoryMemoryManager:
    """感覚記憶 (Sensory Memory)。
    生の入力を処理前に一時保持する。

    2系統の入力を扱う:
    - 断片入力: add_fragment / timeout / flush 機構 (debug/tcp_input 等)
    - 確定入力: store_raw で完全な入力を保持 (main pipeline)

    脳科学対応: 感覚野 (sensory cortex) が raw な刺激を
    極短期間保持する処理に相当。
    """

    def __init__(
        self,
        session_id: str = "",
        timeout_ms: int = 800,
        max_fragments: int = 10,
    ):
        self._session_id = session_id
        self._timeout_ms = timeout_ms
        self._max_fragments = max_fragments
        self._fragments: list[str] = []
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._flush_callback: Callable[[str, str], None] | None = None
        self._readiness: ReadinessEvaluator | None = None
        self._closed = False
        self._raw_input: str = ""
        self._raw_timestamp: str = ""

    # ---- fragment mode (debug/tcp_input) ----

    def set_flush_callback(self, callback: Callable[[str, str], None]) -> None:
        self._flush_callback = callback

    def set_readiness_evaluator(self, evaluator: ReadinessEvaluator) -> None:
        self._readiness = evaluator

    def add_fragment(self, content: str, is_final: bool) -> None:
        if self._closed:
            return
        with self._lock:
            self._fragments.append(content)
            if len(self._fragments) >= self._max_fragments:
                self._flush_locked()
                return
            if is_final:
                self._flush_locked()
                return
            readiness = self._readiness
            if readiness is not None and readiness.evaluate(self._fragments, is_final=False):
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
        content = "".join(self._fragments)
        self._fragments.clear()
        if self._flush_callback:
            self._flush_callback(self._session_id, content)

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
            self._raw_input = ""
            self._raw_timestamp = ""

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._cancel_timer_locked()
            self._fragments.clear()
            self._flush_callback = None

    # ---- raw input mode (main pipeline) ----

    def store_raw(self, content: str) -> None:
        self._raw_input = content
        self._raw_timestamp = datetime.now(UTC).isoformat()
        logger.debug("SensoryMemory: stored raw input (len={})", len(content))

    def retrieve(self) -> dict[str, str]:
        result: dict[str, str] = {}
        with self._lock:
            text = "".join(self._fragments)
            if text:
                result["fragment"] = text
        if self._raw_input:
            result["raw"] = self._raw_input
            result["raw_timestamp"] = self._raw_timestamp
        return result

    @property
    def has_pending_raw(self) -> bool:
        return bool(self._raw_input)

    @property
    def last_raw_input(self) -> str:
        return self._raw_input

    @property
    def fragment_count(self) -> int:
        with self._lock:
            return len(self._fragments)

    @property
    def accumulated_text(self) -> str:
        with self._lock:
            return "".join(self._fragments)
