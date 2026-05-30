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
    room_id=None の場合はグローバル抑制として扱う。
    """

    def __init__(
        self,
        gate: _Gate,
        config: InhibitionConfig,
    ) -> None:
        self._gate = gate
        self._cfg = config
        self._suppressed_reasons: dict[tuple[str | None, str], float] = {}

    def _make_key(self, room_id: str | None, reason: str) -> tuple[str | None, str]:
        return (room_id or None, reason)

    # ---- Generic suppression API ----

    @property
    def has_active_suppression(self) -> bool:
        now = time.monotonic()
        return any(expiry > now for expiry in self._suppressed_reasons.values())

    def is_suppressed(self, reason: str, room_id: str | None = None) -> bool:
        key = self._make_key(room_id, reason)
        expiry = self._suppressed_reasons.get(key)
        if expiry is None:
            return False
        return time.monotonic() < expiry

    def suppress(self, reason: str, duration: float = 0.0, room_id: str | None = None) -> None:
        key = self._make_key(room_id, reason)
        if duration > 0:
            self._suppressed_reasons[key] = time.monotonic() + duration
        else:
            self._suppressed_reasons[key] = float("inf")
        logger.debug("Striatum: suppress reason={} room={} duration={}", reason, room_id, duration)

    def unsuppress(self, reason: str, room_id: str | None = None) -> None:
        key = self._make_key(room_id, reason)
        self._suppressed_reasons.pop(key, None)
        logger.debug("Striatum: unsuppress reason={} room={}", reason, room_id)

    def evaluate(self, plan: Plan) -> GateDecision:
        now = time.monotonic()

        # HYPERDIRECT: 理由"hyperdirect"が設定されている場合、全Plan拒否
        hyperdirect_key = self._make_key(None, "hyperdirect")
        hyperdirect_expiry = self._suppressed_reasons.get(hyperdirect_key)
        if hyperdirect_expiry is not None and now < hyperdirect_expiry:
            return GateDecision(
                allow=False,
                pathway=Pathway.HYPERDIRECT,
                reason="hyperdirect inhibition active",
            )

        room_id = plan.room_id or None
        if self._gate.is_room_executing(plan.room_id):
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

        if self._gate.is_room_on_cooldown(plan.room_id):
            if plan.reason == PlanReason.USER_INPUT:
                return GateDecision(
                    allow=True,
                    pathway=Pathway.DIRECT,
                    reason="user input queued despite cooldown",
                )
            return GateDecision(
                allow=False,
                pathway=Pathway.INDIRECT,
                reason=f"cooldown remaining",
            )

        for (sup_room, reason), expiry in list(self._suppressed_reasons.items()):
            if reason == "hyperdirect":
                continue
            if now < expiry and plan.reason != PlanReason.USER_INPUT:
                if sup_room is None or sup_room == plan.room_id:
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
                f"{room or 'global'}:{reason}": "permanent" if v == float("inf") else round(v - now, 1)
                for (room, reason), v in self._suppressed_reasons.items()
            },
        }
