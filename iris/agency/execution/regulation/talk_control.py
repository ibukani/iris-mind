from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.agency.execution.regulation.output_tracker import OutputTracker
    from iris.agency.planning.models import Plan


TALKATIVE_ABBREVIATED_THRESHOLD = 1
TALKATIVE_TOKEN_LIMIT_THRESHOLD = 2
TALKATIVE_SKIP_POSTPROCESS_THRESHOLD = 3
TALKATIVE_DISABLE_STREAM_THRESHOLD = 5


@dataclass
class TalkativeAdjustments:
    task_level: str | None = None
    max_tokens: int | None = None
    show_thinking: bool | None = None
    run_reflexion: bool | None = None
    run_compression: bool | None = None


def get_talkative_adjustments(degree: int) -> TalkativeAdjustments:
    adj = TalkativeAdjustments()
    if degree <= 0:
        return adj
    if degree >= TALKATIVE_ABBREVIATED_THRESHOLD:
        adj.task_level = "chat"
    if degree >= TALKATIVE_TOKEN_LIMIT_THRESHOLD:
        adj.max_tokens = 256
    if degree >= TALKATIVE_SKIP_POSTPROCESS_THRESHOLD:
        adj.run_reflexion = False
        adj.run_compression = False
    if degree >= TALKATIVE_DISABLE_STREAM_THRESHOLD:
        adj.show_thinking = False
    return adj


def should_skip_proactive(plan: Plan, degree: int, monitor: OutputTracker | None) -> bool:
    content: str = plan.content
    if content:
        return False
    if not monitor:
        return False
    return degree >= 2 or (monitor.frequency_exceeded and degree >= 1)
