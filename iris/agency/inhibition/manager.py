from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from iris.agency.inhibition.gate import _Gate
from iris.agency.inhibition.models import GateDecision, SuppressionProfile
from iris.agency.inhibition.striatum import _Striatum

if TYPE_CHECKING:
    from iris.agency.planning.models import Plan
    from iris.kernel.config import InhibitionConfig


class InhibitionManager:
    """SNc analog: 抑制系全体の統括Facade。

    Striatum (Plan評価) + Gate (実行権制御) を統合し、
    Agency層の抑制制御を一元提供する。
    抑制要因は全て理由キー付きで一元管理。
    """

    def __init__(
        self,
        config: InhibitionConfig,
        session_getter: Callable[[], bool] | None = None,
    ) -> None:
        self._cfg = config
        self._gate = _Gate(config)
        self._striatum = _Striatum(self._gate, config)
        self._session_getter = session_getter

    # ---- Plan evaluation (Striatum) ----

    def evaluate(self, plan: Plan) -> GateDecision:
        return self._striatum.evaluate(plan)

    def should_suppress_proactive(self, room_id: str = "") -> bool:
        if room_id:
            is_executing = self._gate.is_room_executing(room_id)
            is_on_cooldown = self._gate.is_room_on_cooldown(room_id)
        else:
            is_executing = self._gate.is_executing
            is_on_cooldown = self._gate.is_on_cooldown
        return (
            (self._cfg.inhibit_proactive_during_execution and is_executing)
            or (self._cfg.inhibit_proactive_during_cooldown and is_on_cooldown)
            or self._striatum.has_active_suppression
            or (self._session_getter is not None and not self._session_getter())
        )

    def should_suppress(self, plan_reason: str, room_id: str | None = None) -> bool:
        """指定された plan_reason が現在の抑制状態でブロックされるかを判定する。"""
        return self._striatum.should_suppress(plan_reason, room_id)

    # ---- Execution gate (Gate) ----

    def acquire_execution(self, room_id: str = "") -> GateDecision:
        return self._gate.acquire(room_id)

    def release_execution(self, room_id: str = "") -> None:
        self._gate.release(room_id)

    def force_release_execution(self, room_id: str = "") -> None:
        self._gate.force_release(room_id)

    # ---- Queries ----

    def is_executing(self, room_id: str = "") -> bool:
        if room_id:
            return self._gate.is_room_executing(room_id)
        return self._gate.is_executing

    def is_on_cooldown(self, room_id: str = "") -> bool:
        if room_id:
            return self._gate.is_room_on_cooldown(room_id)
        return self._gate.is_on_cooldown

    def is_suppressed(self, reason: str, room_id: str | None = None) -> bool:
        return self._striatum.is_suppressed(reason, room_id)

    # ---- Generic suppression API ----

    def suppress(
        self,
        reason: str,
        duration: float = 0.0,
        room_id: str | None = None,
        profile: SuppressionProfile | None = None,
    ) -> None:
        self._striatum.suppress(reason, duration, room_id, profile)

    def unsuppress(self, reason: str, room_id: str | None = None) -> None:
        self._striatum.unsuppress(reason, room_id)

    def get_active_suppressions(self) -> list[dict]:
        return self._striatum.get_active_suppressions()

    # ---- Diagnostics ----

    def get_state(self) -> dict:
        return {
            "gate": self._gate.get_state(),
            "striatum": self._striatum.get_state(),
        }
