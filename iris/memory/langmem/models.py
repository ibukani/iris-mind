from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field

JobStatus = Literal["pending", "running", "succeeded", "failed", "skipped"]
CandidateStatus = Literal["pending", "promoted", "rejected", "needs_review"]
TargetStore = Literal["semantic", "episodic", "relationship", "appraisal", "style", "persona_patch"]
PassType = Literal["semantic", "episodic", "style", "appraisal", "relationship", "persona_patch"]


class MemoryExtractionJob(BaseModel):
    """1 つの抽出ジョブを表す。

    - source_record_ids: 入力元 RawArchive レコードの ID 群
    - pass_type: 抽出パス (semantic / episodic / style / appraisal / relationship)
    - retry_count: 失敗時のみインクリメント
    - account_id / room_id: このジョブが対象とするスコープ (重複検出にも利用)
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: JobStatus = "pending"
    source_record_ids: list[str] = Field(default_factory=list)
    extractor: str = "langmem"
    model: str = ""
    pass_type: PassType = "semantic"
    retry_count: int = 0
    error: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    account_id: str = ""
    room_id: str = ""


class MemoryCandidate(BaseModel):
    """LangMem の出力 (あるいは手動作成) を 1 候補として保持する中間データ。

    promotion_policy が ``payload`` を検証し、適切なストアへ昇格する。
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_record_ids: list[str] = Field(default_factory=list)
    job_id: str = ""
    target_store: TargetStore = "semantic"
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    status: CandidateStatus = "pending"
    rejection_reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = ""
    scope_account_id: str = ""
    scope_room_id: str = ""


__all__ = [
    "CandidateStatus",
    "JobStatus",
    "MemoryCandidate",
    "MemoryExtractionJob",
    "PassType",
    "TargetStore",
]
