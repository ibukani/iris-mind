from __future__ import annotations

from datetime import UTC, datetime
import uuid

from pydantic import BaseModel, Field


class MemoryConsolidationRecord(BaseModel):
    """1 つの consolidation イベントを表す監査ログ。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_record_ids: list[str] = Field(default_factory=list)
    source: str = "raw_conversation"
    extractor: str = "langmem"
    schema_version: str = "1"
    candidate_ids: list[str] = Field(default_factory=list)
    created_memory_ids: list[str] = Field(default_factory=list)
    rejected_candidate_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    notes: str = ""


__all__ = ["MemoryConsolidationRecord"]
