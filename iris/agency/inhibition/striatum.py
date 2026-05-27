from __future__ import annotations

import time
from typing import TYPE_CHECKING

from iris.agency.inhibition.models import GateDecision, Pathway
from iris.agency.planning.models import Plan, PlanReason

if TYPE_CHECKING:
    from iris.agency.inhibition.gate import _Gate
    from iris.kernel.config import InhibitionConfig

from loguru import logger


class _Striatum:
    """Striatum analog: Plan受理 + 競合検出 + Go/No-go判定。

    Plan (PFC由来) を受け取り、抑制状態と照合して経路選択:
    - DIRECT: 実行許可
    - INDIRECT: 選択的抑制（cooldown/実行中/外部抑制要因）
    - HYPERDIRECT: 緊急停止時は全拒否（USER_INPUT含む）

    抑制要因は全て理由キー付きで _suppressed_reasons に一元管理。
    voice_recording, emotional_fatigue 等は全て同じ仕組み。
    """

    def __init__(
        self,
        gate: _Gate,
        config: InhibitionConfig,
    ) -> None:
        self._gate = gate
        self._cfg = config
        self._suppressed_reasons: dict[str, float] = {}

    # ---- Generic suppression API ----

    @property
    def has_active_suppression(self) -> bool:
        now = time.monotonic()
        return any(expiry > now for expiry in self._suppressed_reasons.values())

    def is_suppressed(self, reason: str) -> bool:
        expiry = self._suppressed_reasons.get(reason)
        if expiry is None:
            return False
        return time.monotonic() < expiry

    def suppress(self, reason: str, duration: float = 0.0) -> None:
        if duration > 0:
            self._suppressed_reasons[reason] = time.monotonic() + duration
        else:
            self._suppressed_reasons[reason] = float("inf")
        logger.debug("Striatum: suppress reason={} duration={}", reason, duration)

    def unsuppress(self, reason: str) -> None:
        self._suppressed_reasons.pop(reason, None)
        logger.debug("Striatum: unsuppress reason={}", reason)

    def evaluate(self, plan: Plan) -> GateDecision:
        now = time.monotonic()

        # HYPERDIRECT: 理由"hyperdirect"が設定されている場合、全Plan拒否
        hyperdirect_expiry = self._suppressed_reasons.get("hyperdirect")
        if hyperdirect_expiry is not None and now < hyperdirect_expiry:
            return GateDecision(
                allow=False,
                pathway=Pathway.HYPERDIRECT,
                reason="hyperdirect inhibition active",
            )

        if self._gate.is_executing:
            if plan.reason == PlanReason.USER_INPUT:
                return GateDecision(
                    allow=True,
                    pathway=Pathway.DIRECT,
                    reason="user input queued despite execution in progress",
                )
            return GateDecision(
                allow=False,
                pathway=Pathway.INDIRECT,
                reason="execution in progress",
            )

        if self._gate.is_on_cooldown:
            if plan.reason == PlanReason.USER_INPUT:
                return GateDecision(
                    allow=True,
                    pathway=Pathway.DIRECT,
                    reason="user input queued despite cooldown",
                )
            return GateDecision(
                allow=False,
                pathway=Pathway.INDIRECT,
                reason=f"cooldown {self._gate.remaining_cooldown:.1f}s remaining",
            )

        for reason, expiry in list(self._suppressed_reasons.items()):
            if reason == "hyperdirect":
                continue
            if now < expiry and plan.reason != PlanReason.USER_INPUT:
                return GateDecision(
                    allow=False,
                    pathway=Pathway.INDIRECT,
                    reason=f"suppressed: {reason}",
                )

        return GateDecision(
            allow=True,
            pathway=Pathway.DIRECT,
            reason="gate open",
        )

    def get_state(self) -> dict:
        now = time.monotonic()
        return {
            "suppressed_reasons": {
                k: "permanent" if v == float("inf") else round(v - now, 1) for k, v in self._suppressed_reasons.items()
            },
        }
