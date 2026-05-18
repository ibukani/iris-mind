from __future__ import annotations

import logging
from typing import Any

from iris.memory.sensory.buffer import InputBuffer

logger = logging.getLogger(__name__)


class SensoryMemoryManager:
    """感覚記憶 (Sensory Memory)。
    InputBuffer をラップし、生の入力断片を一時保持する。
    保持期間はミリ秒単位で、フラッシュ後は破棄される。
    """

    def __init__(self, buffer: InputBuffer | None = None):
        self._buffer = buffer

    def set_buffer(self, buf: InputBuffer) -> None:
        self._buffer = buf

    def store(self, data: Any) -> None:
        if self._buffer is None:
            return
        if isinstance(data, str):
            self._buffer.add_fragment(data, is_final=True)
        elif isinstance(data, dict) and "text" in data:
            self._buffer.add_fragment(data["text"], is_final=True)

    def retrieve(self) -> dict[str, str]:
        if self._buffer is None:
            return {}
        return {"text": self._buffer.accumulated_text}

    def clear(self) -> None:
        if self._buffer is not None:
            self._buffer.close()
