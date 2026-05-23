from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict

if TYPE_CHECKING:
    from iris.llm.interrupt_token import InterruptToken

from langchain_core.messages import BaseMessage


class ExecutionState(TypedDict):
    plan: dict[str, Any]
    messages: list[BaseMessage]
    response_text: NotRequired[str]
    tool_iterations: int
    interrupted: bool
    error: NotRequired[str | None]
    completed: bool


@dataclass
class DynamicState:
    on_token: Callable[[str], None] | None = None
    interrupt_token: InterruptToken | None = None
