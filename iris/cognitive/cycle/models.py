from dataclasses import dataclass
from enum import StrEnum

from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.actions import ActionPlan


class StepStatus(StrEnum):
    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class PipelineStepResult:
    step_name: str
    status: StepStatus
    reason: str | None = None


@dataclass(frozen=True)
class PerceptionResult(PipelineStepResult):
    text: str | None = None
    language: str | None = None
    intent_hint: str | None = None


@dataclass(frozen=True)
class MemoryRetrievalResult(PipelineStepResult):
    relevant_facts: tuple[str, ...] = ()
    relevant_episodes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AppraisalResult(PipelineStepResult):
    mood_label: str | None = None
    arousal: float = 0.0
    valence: float = 0.0


@dataclass(frozen=True)
class RelationshipResult(PipelineStepResult):
    user_label: str | None = None
    affinity: float = 0.0
    trust: float = 0.0
    familiarity: float = 0.0


@dataclass(frozen=True)
class MotivationResult(PipelineStepResult):
    goals: tuple[str, ...] = ()


@dataclass(frozen=True)
class PolicyResult(PipelineStepResult):
    constraints: tuple[str, ...] = ()
    response_allowed: bool = True


@dataclass(frozen=True)
class ActionSelectionResult(PipelineStepResult):
    action_plans: tuple[ActionPlan, ...] = ()


@dataclass(frozen=True)
class CycleResult:
    frame: WorkspaceFrame
    selected_plan: ActionPlan
