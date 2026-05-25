from __future__ import annotations

from typing import TYPE_CHECKING

from iris.agency.planning.models import Plan

if TYPE_CHECKING:
    from iris.agency.execution.regulation.output_tracker import OutputTracker


TALKATIVE_ABBREVIATED_THRESHOLD = 1
TALKATIVE_TOKEN_LIMIT_THRESHOLD = 2
TALKATIVE_SKIP_POSTPROCESS_THRESHOLD = 3
TALKATIVE_DISABLE_STREAM_THRESHOLD = 5


def apply_talkative_overrides(plan: Plan, degree: int) -> None:
    if degree <= 0:
        return
    if degree >= TALKATIVE_ABBREVIATED_THRESHOLD:
        plan.task_level = "chat"
    if degree >= TALKATIVE_TOKEN_LIMIT_THRESHOLD:
        current = plan.overrides.get("max_tokens", 0)
        if current and current > 0:
            plan.overrides["max_tokens"] = min(current, 256)
    if degree >= TALKATIVE_SKIP_POSTPROCESS_THRESHOLD:
        plan.overrides["run_reflexion"] = False
        plan.overrides["run_compression"] = False
    if degree >= TALKATIVE_DISABLE_STREAM_THRESHOLD:
        plan.overrides["show_thinking"] = False


def should_skip_proactive(plan: Plan, degree: int, monitor: OutputTracker | None) -> bool:
    content: str = plan.content
    if content:
        return False
    if not monitor:
        return False
    return degree >= 2 or (monitor.frequency_exceeded and degree >= 1)
