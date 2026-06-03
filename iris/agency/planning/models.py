from __future__ import annotations

from enum import StrEnum
from typing import Any, TypedDict

from pydantic import BaseModel, Field

from iris.agency.modulation import ModulationState


class PlanReason(StrEnum):
    USER_INPUT = "user_input"
    PROACTIVE_CURIOSITY = "proactive_curiosity"
    PROACTIVE_ESCALATION = "proactive_escalation"
    TIMER_EVENT = "timer"


class PlanningState(TypedDict):
    strategy_type: str
    proactive_judge_available: bool


class Plan(BaseModel):
    content: str
    task_level: str = "normal"
    silent: bool = False
    reason: PlanReason = PlanReason.USER_INPUT
    context_hint: str = ""
    session_id: str = ""
    account_id: str = ""
    room_id: str = ""
    overrides: dict[str, Any] = Field(default_factory=dict)
    modulation: ModulationState = Field(default_factory=ModulationState)
