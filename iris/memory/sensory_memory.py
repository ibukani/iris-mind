from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any

from iris.memory.sensory.buffer import InputBuffer

logger = logging.getLogger(__name__)


class SensoryMemoryManager:
    """感覚記憶 (Sensory Memory)。
    生の入力を処理前に一時保持する。

    2系統の入力を扱う:
    - store_fragment: InputBuffer 経由の断片入力 (debug/tcp_input)
    - store_raw: 確定した完全な入力を保持 (main pipeline)
    """

    def __init__(self, buffer: InputBuffer | None = None):
        self._buffer = buffer
        self._last_raw_input: str = ""
        self._last_raw_timestamp: str = ""

    def set_buffer(self, buf: InputBuffer) -> None:
        self._buffer = buf

    def store_fragment(self, data: Any) -> None:
        if self._buffer is None:
            return
        if isinstance(data, str):
            self._buffer.add_fragment(data, is_final=True)
        elif isinstance(data, dict) and "text" in data:
            self._buffer.add_fragment(data["text"], is_final=True)

    def store_raw(self, content: str) -> None:
        self._last_raw_input = content
        self._last_raw_timestamp = datetime.now(UTC).isoformat()
        logger.debug("SensoryMemory: stored raw input (len=%d)", len(content))

    def retrieve(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if self._buffer is not None:
            text = self._buffer.accumulated_text
            if text:
                result["fragment"] = text
        if self._last_raw_input:
            result["raw"] = self._last_raw_input
            result["raw_timestamp"] = self._last_raw_timestamp
        return result

    @property
    def has_pending_raw(self) -> bool:
        return bool(self._last_raw_input)

    @property
    def last_raw_input(self) -> str:
        return self._last_raw_input

    def clear(self) -> None:
        self._last_raw_input = ""
        self._last_raw_timestamp = ""
        if self._buffer is not None:
            self._buffer.close()
