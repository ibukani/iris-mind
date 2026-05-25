from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, NotRequired, TypedDict

from langchain_core.messages import BaseMessage

from iris.agency.execution.regulation.talk_control import TalkativeAdjustments
from iris.agency.planning.models import Plan

if TYPE_CHECKING:
    from iris.llm.interrupt_token import InterruptToken


class ExecutionState(TypedDict):
    plan: Plan
    messages: list[BaseMessage]
    response_text: NotRequired[str]
    tool_iterations: int
    interrupted: bool
    error: NotRequired[str | None]
    completed: bool
    current_node_type: str
    current_level_idx: int
    chain_depth: int
    talkative_adjustments: NotRequired[TalkativeAdjustments]


@dataclass
class DynamicState:
    on_token: Callable[[str], None] | None = None
    interrupt_token: InterruptToken | None = None
