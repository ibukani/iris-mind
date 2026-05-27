from __future__ import annotations

from typing import TYPE_CHECKING

from iris.agency.inhibition.gate import _Gate
from iris.agency.inhibition.models import GateDecision
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

    def __init__(self, config: InhibitionConfig) -> None:
        self._cfg = config
        self._gate = _Gate(config)
        self._striatum = _Striatum(self._gate, config)

    # ---- Plan evaluation (Striatum) ----

    def evaluate(self, plan: Plan) -> GateDecision:
        return self._striatum.evaluate(plan)

    def should_suppress_proactive(self) -> bool:
        return (
            (self._cfg.inhibit_proactive_during_execution and self._gate.is_executing)
            or (self._cfg.inhibit_proactive_during_cooldown and self._gate.is_on_cooldown)
            or self._striatum.has_active_suppression
        )

    # ---- Execution gate (Gate) ----

    def acquire_execution(self) -> GateDecision:
        return self._gate.acquire()

    def release_execution(self) -> None:
        self._gate.release()

    def force_release_execution(self) -> None:
        self._gate.force_release()

    # ---- Queries ----

    @property
    def is_executing(self) -> bool:
        return self._gate.is_executing

    @property
    def is_on_cooldown(self) -> bool:
        return self._gate.is_on_cooldown

    def is_suppressed(self, reason: str) -> bool:
        return self._striatum.is_suppressed(reason)

    # ---- Generic suppression API ----

    def suppress(self, reason: str, duration: float = 0.0) -> None:
        self._striatum.suppress(reason, duration)

    def unsuppress(self, reason: str) -> None:
        self._striatum.unsuppress(reason)

    # ---- Diagnostics ----

    def get_state(self) -> dict:
        return {
            "gate": self._gate.get_state(),
            "striatum": self._striatum.get_state(),
        }
