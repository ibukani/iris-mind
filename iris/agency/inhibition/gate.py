from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from iris.agency.inhibition.models import GateDecision, Pathway

if TYPE_CHECKING:
    from iris.kernel.config import InhibitionConfig

from loguru import logger


class _RoomGate:
    """Room-level gate: 実行権の排他制御 + cooldown管理。"""

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
                "RoomGate: execution released, cooldown {}s",
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


class _Gate:
    """GPi/SNr analog: ルーム別の実行権排他制御 + cooldown管理。"""

    def __init__(self, config: InhibitionConfig) -> None:
        self._cfg = config
        self._gates: dict[str, _RoomGate] = {}
        self._global_gate = _RoomGate(config)

    def _get_gate(self, room_id: str = "") -> _RoomGate:
        if not room_id:
            return self._global_gate
        return self._gates.setdefault(room_id, _RoomGate(self._cfg))

    @property
    def is_executing(self) -> bool:
        return self._global_gate.is_executing or any(g.is_executing for g in self._gates.values())

    @property
    def is_on_cooldown(self) -> bool:
        return self._global_gate.is_on_cooldown or any(g.is_on_cooldown for g in self._gates.values())

    def acquire(self, room_id: str = "") -> GateDecision:
        return self._get_gate(room_id).acquire()

    def release(self, room_id: str = "") -> None:
        self._get_gate(room_id).release()

    def force_release(self, room_id: str = "") -> None:
        self._get_gate(room_id).force_release()

    def is_room_executing(self, room_id: str) -> bool:
        return self._get_gate(room_id).is_executing

    def is_room_on_cooldown(self, room_id: str) -> bool:
        return self._get_gate(room_id).is_on_cooldown

    def get_state(self) -> dict:
        return {
            "global": self._global_gate.get_state(),
            "rooms": {rid: g.get_state() for rid, g in self._gates.items()},
        }
