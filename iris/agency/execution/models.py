from __future__ import annotations

from collections.abc import Callable
from typing import NotRequired, TypedDict

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict

from iris.agency.planning.models import Plan
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


class ExecutionStateInfo(TypedDict):
    msg_count: int


class DynamicState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    on_token: Callable[[str], None] | None = None
    interrupt_token: InterruptToken | None = None
    current_plan: Plan | None = None
