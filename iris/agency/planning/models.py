from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from iris.agency.modulation import ModulationState


class PlanReason(StrEnum):
    USER_INPUT = "user_input"
    PROACTIVE_CURIOSITY = "proactive_curiosity"
    PROACTIVE_ESCALATION = "proactive_escalation"
    TIMER_EVENT = "timer"


@dataclass
class Plan:
    content: str
    task_level: str = "normal"
    silent: bool = False
    reason: PlanReason = PlanReason.USER_INPUT
    context_hint: str = ""
    session_id: str = ""
    user_id: str = ""
    room_id: str = ""
    overrides: dict[str, Any] = field(default_factory=dict)
    modulation: ModulationState = field(default_factory=ModulationState)
