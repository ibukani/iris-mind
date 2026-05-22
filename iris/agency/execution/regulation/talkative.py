from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.agency.execution.regulation.monitor import OutputMonitor


TALKATIVE_ABBREVIATED_THRESHOLD = 1
TALKATIVE_TOKEN_LIMIT_THRESHOLD = 2
TALKATIVE_SKIP_POSTPROCESS_THRESHOLD = 3
TALKATIVE_DISABLE_STREAM_THRESHOLD = 5


def apply_talkative_overrides(plan: dict[str, Any]) -> None:
    degree: int = plan.get("talkative_degree", 0)
    if degree <= 0:
        return
    if degree >= TALKATIVE_ABBREVIATED_THRESHOLD:
        plan["abbreviated"] = True
    if degree >= TALKATIVE_TOKEN_LIMIT_THRESHOLD:
        current = plan.get("max_tokens", 0)
        if current > 0:
            plan["max_tokens"] = min(current, 256)
    if degree >= TALKATIVE_SKIP_POSTPROCESS_THRESHOLD:
        plan["run_reflexion"] = False
        plan["run_compression"] = False
    if degree >= TALKATIVE_DISABLE_STREAM_THRESHOLD:
        plan["streaming"] = False
        plan["show_thinking"] = False


def should_skip_proactive(plan: dict[str, Any], monitor: OutputMonitor | None) -> bool:
    content: str = plan.get("content", "")
    if content:
        return False
    if not monitor:
        return False
    talkative: int = plan.get("talkative_degree", 0) or monitor.talkative_degree
    return talkative >= 2 or (monitor.frequency_exceeded and talkative >= 1)
