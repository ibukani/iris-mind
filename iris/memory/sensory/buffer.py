from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class InputBuffer:
    session_id: str
    timeout_ms: int = 800
    max_fragments: int = 10

    _fragments: list[str] = field(default_factory=list, repr=False)
    _timer: threading.Timer | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _flush_callback: Callable[[str, str], None] | None = field(default=None, repr=False)
    _closed: bool = field(default=False, repr=False)

    def set_flush_callback(self, callback: Callable[[str, str], None]) -> None:
        self._flush_callback = callback

    def add_fragment(self, content: str, is_final: bool) -> None:
        if self._closed:
            return

        with self._lock:
            self._fragments.append(content)
            if len(self._fragments) >= self.max_fragments:
                self._flush_locked()
                return

        if is_final:
            self.flush()
        else:
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
        cb = self._flush_callback

        if cb:
            cb(self.session_id, content)

    def _reset_timer(self) -> None:
        with self._lock:
            self._cancel_timer_locked()
            if self.timeout_ms > 0:
                self._timer = threading.Timer(
                    self.timeout_ms / 1000,
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

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._cancel_timer_locked()
            self._fragments.clear()
            self._flush_callback = None

    @property
    def fragment_count(self) -> int:
        with self._lock:
            return len(self._fragments)

    @property
    def accumulated_text(self) -> str:
        with self._lock:
            return "".join(self._fragments)
