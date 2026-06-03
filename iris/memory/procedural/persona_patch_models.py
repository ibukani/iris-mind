from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field

PersonaPatchStatus = Literal["pending", "approved", "rejected", "applied"]


class PersonaPatchCandidate(BaseModel):
    """提案された .iris/config/iris_profile.md への変更案。

    自動適用しない。承認フローでのみ適用される。
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    target_file: str = ".iris/config/iris_profile.md"
    reason: str = ""
    proposed_patch: str = ""
    evidence_record_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    status: PersonaPatchStatus = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["PersonaPatchCandidate", "PersonaPatchStatus"]
