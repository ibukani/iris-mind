from __future__ import annotations

import time
from typing import TYPE_CHECKING

from iris.agency.inhibition.models import (
    BUILTIN_SUPPRESSION_PROFILES,
    ActiveSuppression,
    GateDecision,
    Pathway,
    SuppressionEntry,
    SuppressionProfile,
    SuppressionState,
)
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

    抑制要因は全て理由キー付きで _suppressions に一元管理。
    各エントリは SuppressionProfile を持ち、blocked_reasons で
    どの PlanReason を持つ Plan をブロックするかを制御する。
    """

    def __init__(
        self,
        gate: _Gate,
        config: InhibitionConfig,
        profiles: dict[str, SuppressionProfile] | None = None,
    ) -> None:
        self._gate = gate
        self._cfg = config
        self._profiles = profiles or dict(BUILTIN_SUPPRESSION_PROFILES)
        self._suppressions: dict[str, SuppressionEntry] = {}

    def _make_key(self, room_id: str | None, reason: str) -> str:
        return f"{room_id or '_global_'}:{reason}"

    # ---- Generic suppression API ----

    @property
    def has_active_suppression(self) -> bool:
        now = time.monotonic()
        return any(e.expiry == 0.0 or e.expiry > now for e in self._suppressions.values())

    def is_suppressed(self, reason: str, room_id: str | None = None) -> bool:
        key = self._make_key(room_id, reason)
        entry = self._suppressions.get(key)
        if entry is None:
            return False
        if entry.expiry == 0.0:
            return True
        return time.monotonic() < entry.expiry

    def suppress(
        self,
        reason: str,
        duration: float = 0.0,
        room_id: str | None = None,
        profile: SuppressionProfile | None = None,
    ) -> None:
        key = self._make_key(room_id, reason)
        if profile is None:
            profile = self._profiles.get(reason, SuppressionProfile(blocked_reasons=frozenset(), priority=1))
        expiry = time.monotonic() + duration if duration > 0 else 0.0
        self._suppressions[key] = SuppressionEntry(
            reason=reason,
            profile=profile,
            room_id=room_id,
            expiry=expiry,
        )
        logger.debug(
            "Striatum: suppress reason={} room={} duration={} blocked={}",
            reason,
            room_id,
            duration,
            profile.blocked_reasons,
        )

    def unsuppress(self, reason: str, room_id: str | None = None) -> None:
        key = self._make_key(room_id, reason)
        self._suppressions.pop(key, None)
        logger.debug("Striatum: unsuppress reason={} room={}", reason, room_id)

    def should_suppress(self, plan_reason: str, room_id: str | None = None) -> bool:
        """指定された plan_reason が現在の抑制状態でブロックされるかを判定する。"""
        now = time.monotonic()
        for entry in self._suppressions.values():
            is_active = entry.expiry == 0.0 or now < entry.expiry
            if not is_active:
                continue
            if entry.room_id is not None and entry.room_id != room_id:
                continue
            if plan_reason in entry.profile.blocked_reasons:
                return True
        return False

    def get_active_suppressions(self) -> list[dict[str, object]]:
        now = time.monotonic()
        result: list[dict[str, object]] = []
        for entry in self._suppressions.values():
            if entry.expiry == 0.0 or now < entry.expiry:
                remaining: float | str = "permanent" if entry.expiry == 0.0 else round(entry.expiry - now, 1)
                snapshot = ActiveSuppression(
                    reason=entry.reason,
                    room_id=entry.room_id,
                    priority=entry.profile.priority,
                    blocked_reasons=list(entry.profile.blocked_reasons),
                    remaining=remaining,
                )
                result.append(snapshot.to_dict())
        return result

    def evaluate(self, plan: Plan) -> GateDecision:
        now = time.monotonic()

        # HYPERDIRECT: hyperdirect エントリが存在し、blocked_reasons に plan.reason を含む場合
        hyperdirect_key = self._make_key(None, "hyperdirect")
        hyperdirect_entry = self._suppressions.get(hyperdirect_key)
        if hyperdirect_entry is not None:
            is_active = hyperdirect_entry.expiry == 0.0 or now < hyperdirect_entry.expiry
            if is_active and plan.reason.value in hyperdirect_entry.profile.blocked_reasons:
                return GateDecision(
                    allow=False,
                    pathway=Pathway.HYPERDIRECT,
                    reason="hyperdirect inhibition active",
                )

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
                reason="cooldown remaining",
            )

        # プロファイルベースの抑制照合
        for entry in self._suppressions.values():
            if entry.reason == "hyperdirect":
                continue
            is_active = entry.expiry == 0.0 or now < entry.expiry
            if not is_active:
                continue
            if entry.room_id is not None and entry.room_id != plan.room_id:
                continue
            if plan.reason.value not in entry.profile.blocked_reasons:
                continue
            return GateDecision(
                allow=False,
                pathway=Pathway.INDIRECT,
                reason=f"suppressed: {entry.reason}",
            )

        return GateDecision(
            allow=True,
            pathway=Pathway.DIRECT,
            reason="gate open",
        )

    def get_state(self) -> SuppressionState:
        now = time.monotonic()
        return SuppressionState(
            suppressions={
                key: {
                    "reason": entry.reason,
                    "room_id": entry.room_id,
                    "priority": entry.profile.priority,
                    "remaining": ("permanent" if entry.expiry == 0.0 else round(entry.expiry - now, 1)),
                }
                for key, entry in self._suppressions.items()
            },
        )
