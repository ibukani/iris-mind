from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from iris.agency.inhibition.models import GateDecision, Pathway

if TYPE_CHECKING:
    from iris.kernel.config import InhibitionConfig

from loguru import logger


class _Gate:
    """GPi/SNr analog: 実行権の排他制御 + cooldown管理。

    DIRECT pathway (disinhibition) → 実行権付与
    INDIRECT pathway (tonic inhibition) → cooldown
    """

    def __init__(self, config: InhibitionConfig) -> None:
        self._cfg = config
        self._lock = threading.Lock()
        self._executing: bool = False
        self._cooldown_until: float = 0.0

    @property
    def is_executing(self) -> bool:
        return self._executing

    @property
    def is_on_cooldown(self) -> bool:
        return time.monotonic() < self._cooldown_until

    @property
    def remaining_cooldown(self) -> float:
        remaining = self._cooldown_until - time.monotonic()
        return max(0.0, remaining)

    def acquire(self) -> GateDecision:
        with self._lock:
            if self._executing:
                return GateDecision(
                    allow=False,
                    pathway=Pathway.INDIRECT,
                    reason="execution already in progress",
                )
            if self.is_on_cooldown:
                return GateDecision(
                    allow=False,
                    pathway=Pathway.INDIRECT,
                    reason=f"cooldown {self.remaining_cooldown:.1f}s remaining",
                )
            self._executing = True
            return GateDecision(
                allow=True,
                pathway=Pathway.DIRECT,
                reason="gate open",
            )

    def release(self) -> None:
        with self._lock:
            self._executing = False
            self._cooldown_until = time.monotonic() + self._cfg.post_execution_cooldown_sec
            logger.debug(
                "Gate: execution released, cooldown {}s",
                self._cfg.post_execution_cooldown_sec,
            )

    def force_release(self) -> None:
        with self._lock:
            self._executing = False
            self._cooldown_until = 0.0

    def get_state(self) -> dict:
        return {
            "executing": self._executing,
            "cooldown_remaining": self.remaining_cooldown,
        }
