"""Constructor-injection-only composition for cognitive module dependencies.

This module wires PipelineStep instances into a CognitiveCycle.
No service locator, no global registry, no cognitive policy logic.
"""

from collections.abc import Sequence

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import PipelineStepResult
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.cycle.service import CognitiveCycle
from iris.contracts.actions import ActionPlan


def wire_cognitive_cycle(
    steps: Sequence[PipelineStep[PipelineStepResult]],
    fallback_plan: ActionPlan | None = None,
) -> CognitiveCycle:
    if fallback_plan is None:
        fallback_plan = ActionPlan(
            turn_intent="no_action",
            candidate_text=None,
            should_respond=False,
            priority=-1,
        )
    return CognitiveCycle(
        steps=steps,
        frame_builder=FrameBuilder(),
        fallback_plan=fallback_plan,
    )
