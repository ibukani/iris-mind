from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import BaseMessage

from iris.agency.execution.node_types import NODE_TYPES
from iris.agency.execution.regulation.talk_control import (
    get_talkative_adjustments,
    should_skip_proactive,
)
from iris.agency.execution.state import ExecutionState

if TYPE_CHECKING:
    from iris.agency.execution.regulation.output_tracker import OutputTracker
    from iris.agency.inhibition import InhibitionController
    from iris.agency.planning.models import Plan


def build_execution_state(
    plan: Plan,
    messages: list[BaseMessage],
    monitor: OutputTracker | None,
    inhibition: InhibitionController | None,
) -> ExecutionState:
    """Plan + 各種状態から ExecutionState を生成する。"""
    degree = monitor.talkative_degree if monitor else 0
    adj = get_talkative_adjustments(degree)
    entry = adj.task_level or plan.task_level
    nt = NODE_TYPES["general_chat"]
    if entry not in nt.available_levels:
        entry = nt.entry_level
    level_idx = nt.available_levels.index(entry)

    return ExecutionState(
        plan=plan,
        messages=messages,
        response_text="",
        tool_iterations=0,
        interrupted=False,
        error=None,
        completed=False,
        current_node_type="general_chat",
        current_level_idx=level_idx,
        chain_depth=0,
        talkative_adjustments=adj,
    )


def should_skip_plan(
    plan: Plan,
    monitor: OutputTracker | None,
) -> bool:
    """Plan がプロアクティブ抑制によりスキップされるべきかを判定する。"""
    if plan.content:
        return False
    if not monitor:
        return False
    return should_skip_proactive(plan, monitor.talkative_degree, monitor)
