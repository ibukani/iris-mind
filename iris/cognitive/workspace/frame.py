from __future__ import annotations

from dataclasses import dataclass, field

from iris.contracts.actions import ActionPlan
from iris.contracts.memory import MemorySearchResult
from iris.contracts.observations import Observation


@dataclass(frozen=True)
class InterpretedInput:
    text: str | None
    language: str | None
    intent_hint: str | None = None


@dataclass(frozen=True)
class MemorySummary:
    retrieved_memories: tuple[MemorySearchResult, ...] = ()


@dataclass(frozen=True)
class AffectSnapshot:
    mood_label: str | None = None
    arousal: float = 0.0
    valence: float = 0.0
    dominance: float = 0.0
    affect_summary: str | None = None


@dataclass(frozen=True)
class RelationshipSnapshot:
    user_label: str | None = None
    affinity: float = 0.0
    trust: float = 0.0
    familiarity: float = 0.0
    relationship_summary: str | None = None


@dataclass(frozen=True)
class GoalCandidate:
    name: str
    reason: str
    priority: int


@dataclass(frozen=True)
class PolicyConstraint:
    name: str
    reason: str
    blocks_response: bool = False


@dataclass(frozen=True)
class WorkspaceFrame:
    observation: Observation
    interpreted_input: InterpretedInput | None = None
    memory_summary: MemorySummary = field(default_factory=MemorySummary)
    affect: AffectSnapshot = field(default_factory=AffectSnapshot)
    relationship: RelationshipSnapshot = field(default_factory=RelationshipSnapshot)
    goals: tuple[GoalCandidate, ...] = ()
    constraints: tuple[PolicyConstraint, ...] = ()
    candidate_action_plans: tuple[ActionPlan, ...] = ()
