from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InterruptToken:
    _cancelled: bool = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled
