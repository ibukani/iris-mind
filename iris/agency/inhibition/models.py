from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypedDict


class Pathway(StrEnum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    HYPERDIRECT = "hyperdirect"


@dataclass
class GateDecision:
    allow: bool
    pathway: Pathway
    reason: str | None = None


@dataclass(frozen=True)
class SuppressionProfile:
    """抑制プロファイル: 特定の理由で有効化されたとき、どの PlanReason を持つ Plan をブロックするかを定義する。"""

    blocked_reasons: frozenset[str]
    priority: int = 1


@dataclass
class SuppressionEntry:
    """実際に登録されている抑制エントリ。"""

    reason: str
    profile: SuppressionProfile
    room_id: str | None = None
    expiry: float = 0.0  # time.monotonic() の絶対時刻。0.0 は永続


@dataclass
class ActiveSuppression:
    """現在アクティブな抑制状態のスナップショット。"""

    reason: str
    room_id: str | None
    priority: int
    blocked_reasons: list[str] = field(default_factory=list)
    remaining: float | str = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "reason": self.reason,
            "room_id": self.room_id,
            "priority": self.priority,
            "blocked_reasons": list(self.blocked_reasons),
            "remaining": self.remaining,
        }


class SuppressionStateEntry(TypedDict):
    reason: str
    room_id: str | None
    priority: int
    remaining: float | str


class SuppressionState(TypedDict):
    suppressions: dict[str, SuppressionStateEntry]


class RoomGateState(TypedDict):
    executing: bool
    cooldown_remaining: float


class GateState(TypedDict):
    global_state: RoomGateState
    rooms: dict[str, RoomGateState]


class InhibitionState(TypedDict):
    gate: GateState
    striatum: SuppressionState


class PlanningState(TypedDict):
    strategy_type: str
    proactive_judge_available: bool


class ExecutionStateInfo(TypedDict):
    msg_count: int


class AgencyState(TypedDict, total=False):
    planning: PlanningState
    execution: ExecutionStateInfo
    inhibition: InhibitionState


def _proactive_only() -> frozenset[str]:
    from iris.agency.planning.models import PlanReason

    return frozenset({PlanReason.PROACTIVE_CURIOSITY, PlanReason.PROACTIVE_ESCALATION, PlanReason.TIMER_EVENT})


def _all_reasons() -> frozenset[str]:
    from iris.agency.planning.models import PlanReason

    return frozenset({r.value for r in PlanReason})


BUILTIN_SUPPRESSION_PROFILES: dict[str, SuppressionProfile] = {
    "speaking": SuppressionProfile(blocked_reasons=_proactive_only(), priority=1),
    "voice_recording": SuppressionProfile(blocked_reasons=_proactive_only(), priority=2),
    "emotional_fatigue": SuppressionProfile(blocked_reasons=_proactive_only(), priority=1),
    "user_away": SuppressionProfile(blocked_reasons=_proactive_only(), priority=1),
    "hyperdirect": SuppressionProfile(blocked_reasons=_all_reasons(), priority=100),
}
