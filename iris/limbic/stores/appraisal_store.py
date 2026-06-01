"""AppraisalEpisodeStore — Limbic の appraisal/感情/関係性の履歴を append-only 保存する。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import uuid

from pydantic import BaseModel, Field

from iris.limbic.models import EmotionResult, Mood, RelationshipState
from iris.memory.langmem.stores import _IdIndexedJsonlStore


class AppraisalEpisode(BaseModel):
    """1 ターンの appraisal + emotion + relationship のスナップショット。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    account_id: str = ""
    room_id: str = ""
    input_record_id: str = ""
    trigger_summary: str = ""
    context_type: str = ""
    appraisal: dict[str, Any] = Field(default_factory=dict)
    emotion: dict[str, Any] = Field(default_factory=dict)
    mood: Mood = Field(default_factory=Mood)
    relationship_before: RelationshipState = Field(default_factory=RelationshipState)
    relationship_after: RelationshipState = Field(default_factory=RelationshipState)
    reappraisal_needed: bool = False
    reappraisal_suggestion: str = ""

    @classmethod
    def from_result(
        cls,
        result: EmotionResult,
        *,
        account_id: str = "",
        room_id: str = "",
        input_record_id: str = "",
        trigger_summary: str = "",
        context_type: str = "",
        relationship_before: RelationshipState | None = None,
    ) -> AppraisalEpisode:
        return cls(
            account_id=account_id,
            room_id=room_id,
            input_record_id=input_record_id,
            trigger_summary=trigger_summary,
            context_type=context_type,
            appraisal=result.appraisal.model_dump(mode="python"),
            emotion=result.emotion.model_dump(mode="python"),
            mood=result.mood,
            relationship_before=relationship_before or RelationshipState(),
            relationship_after=result.relationship,
            reappraisal_needed=result.reappraisal_needed,
            reappraisal_suggestion=result.reappraisal_suggestion,
        )


class AppraisalEpisodeStore(_IdIndexedJsonlStore[AppraisalEpisode]):
    def __init__(self, path: str) -> None:
        super().__init__(path, AppraisalEpisode)

    def list_for_account(self, account_id: str, limit: int = 50) -> list[AppraisalEpisode]:
        items = [e for e in self.list_all() if e.account_id == account_id]
        return items[-limit:]


__all__ = ["AppraisalEpisode", "AppraisalEpisodeStore"]
