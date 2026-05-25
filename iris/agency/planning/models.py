from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


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
    overrides: dict[str, Any] = field(default_factory=dict)
