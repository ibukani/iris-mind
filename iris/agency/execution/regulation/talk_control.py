from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.agency.execution.regulation.output_tracker import OutputTracker


TALKATIVE_ABBREVIATED_THRESHOLD = 1
TALKATIVE_TOKEN_LIMIT_THRESHOLD = 2
TALKATIVE_SKIP_POSTPROCESS_THRESHOLD = 3
TALKATIVE_DISABLE_STREAM_THRESHOLD = 5


def apply_talkative_overrides(plan: dict[str, Any], degree: int) -> None:
    if degree <= 0:
        return
    if degree >= TALKATIVE_ABBREVIATED_THRESHOLD:
        plan["task_level"] = "chat"
    if degree >= TALKATIVE_TOKEN_LIMIT_THRESHOLD:
        current = plan.get("max_tokens", 0)
        if current and current > 0:
            plan["max_tokens"] = min(current, 256)
    if degree >= TALKATIVE_SKIP_POSTPROCESS_THRESHOLD:
        plan["run_reflexion"] = False
        plan["run_compression"] = False
    if degree >= TALKATIVE_DISABLE_STREAM_THRESHOLD:
        plan["show_thinking"] = False


def should_skip_proactive(plan: dict[str, Any], degree: int, monitor: OutputTracker | None) -> bool:
    content: str = plan.get("content", "")
    if content:
        return False
    if not monitor:
        return False
    return degree >= 2 or (monitor.frequency_exceeded and degree >= 1)
