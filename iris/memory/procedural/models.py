from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
import uuid

from pydantic import BaseModel, Field

StyleKind = Literal[
    "tone_preference",
    "successful_pattern",
    "running_gag",
    "avoidance_rule",
    "chaos_preference",
    "conversation_strategy",
]
StyleScope = Literal["global", "account", "room"]


class StyleMemory(BaseModel):
    """1 件のスタイル/手続き記憶。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    scope: StyleScope = "global"
    account_id: str = ""
    room_id: str = ""
    kind: StyleKind
    content: str
    evidence: str = ""
    confidence: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    last_used_at: str = ""
    enabled: bool = True
    activation_condition: str = ""
    source_record_ids: list[str] = Field(default_factory=list)


__all__ = ["StyleKind", "StyleMemory", "StyleScope"]
