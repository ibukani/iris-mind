"""Minimal application composition root for Cognitive Runtime v1.2.1.

This is the entry point for wiring all layers together.
No cognitive policy logic, no service locator, no global registry.
"""

from collections.abc import Sequence

from iris.cognitive.cycle.models import PipelineStepResult
from iris.cognitive.cycle.pipeline import PipelineStep


class IrisApp:
    def __init__(
        self,
        steps: Sequence[PipelineStep[PipelineStepResult]],
    ) -> None:
        self._steps = tuple(steps)
