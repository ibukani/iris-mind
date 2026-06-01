from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any
import uuid

from pydantic import BaseModel, Field


class LongTermGoal(BaseModel):
    """エージェントの持続的な目標。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    weight: float = 1.0
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def decay(self, amount: float) -> None:
        self.weight = max(0.0, self.weight - amount)
        self.updated_at = time.time()


@dataclass(slots=True)
class EpisodicEntry:
    """エピソード記憶 1 件分の構造化データ。"""

    summary: str
    timestamp: str
    room_id: str = ""
    account_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "summary": self.summary,
            "timestamp": self.timestamp,
            "room_id": self.room_id,
            "account_id": self.account_id,
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EpisodicEntry:
        raw_metadata = data.get("metadata") or {}
        metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
        return cls(
            summary=str(data.get("summary", "")),
            timestamp=str(data.get("timestamp", "")),
            room_id=str(data.get("room_id", "")),
            account_id=str(data.get("account_id", "")),
            metadata=dict(metadata),
        )


@dataclass(slots=True)
class SemanticEntry:
    """意味記憶 1 件分の構造化データ。"""

    content: str
    id: str = ""
    type: str = "lesson"
    tags: list[str] = field(default_factory=list)
    timestamp: str = ""
    room_id: str = ""
    account_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "type": self.type,
            "tags": list(self.tags),
            "timestamp": self.timestamp,
            "room_id": self.room_id,
            "account_id": self.account_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SemanticEntry:
        raw_tags = data.get("tags") or []
        tags: list[str] = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else []
        return cls(
            id=str(data.get("id", "")),
            content=str(data.get("content", "")),
            type=str(data.get("type", "lesson")),
            tags=tags,
            timestamp=str(data.get("timestamp", "")),
            room_id=str(data.get("room_id", "")),
            account_id=str(data.get("account_id", "")),
        )


@dataclass(slots=True)
class EpisodicInput:
    """エピソード記憶への保存入力。"""

    content: str
    kind: str = ""
    metadata: dict[str, Any] | None = None
    room_id: str = ""
    account_id: str = ""


@dataclass(slots=True)
class SemanticInput:
    """意味記憶への保存入力。"""

    content: str
    type: str = "lesson"
    tags: list[str] = field(default_factory=list)
    room_id: str = ""
    account_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "type": self.type,
            "tags": list(self.tags),
            "room_id": self.room_id,
            "account_id": self.account_id,
        }


@dataclass(slots=True)
class SearchHit:
    """意味検索・vector 検索の共通結果型。"""

    content: str
    type: str = "unknown"
    tags: list[str] = field(default_factory=list)
    score: float = 0.0
    timestamp: str = ""
    id: str = ""
    room_id: str = ""
    account_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "type": self.type,
            "tags": list(self.tags),
            "score": round(self.score, 4),
            "timestamp": self.timestamp,
            "id": self.id,
            "room_id": self.room_id,
            "account_id": self.account_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SearchHit:
        raw_tags = data.get("tags") or []
        tags: list[str] = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else []
        return cls(
            content=str(data.get("content", "")),
            type=str(data.get("type", "unknown")),
            tags=tags,
            score=float(data.get("score", 0.0)),
            timestamp=str(data.get("timestamp", "")),
            id=str(data.get("id", "")),
            room_id=str(data.get("room_id", "")),
            account_id=str(data.get("account_id", "")),
        )


@dataclass(slots=True)
class EmotionTag:
    """エピソード記憶に紐づく感情タグ。"""

    emotion: dict[str, float] = field(default_factory=dict)
    intensity: float = 0.0
    type: str = "emotion_tag"


@dataclass(slots=True)
class EmotionMemory:
    """search_emotional() の戻り値型。"""

    entry: EpisodicEntry
    score: float = 0.0
    intensity: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {**self.entry.to_dict(), "score": round(self.score, 4), "intensity": self.intensity}


@dataclass(frozen=True, slots=True)
class EpisodicScope:
    """エピソード記憶の検索スコープ。"""

    room_id: str = ""
    account_id: str = ""


@dataclass(frozen=True, slots=True)
class SemanticScope:
    """意味記憶の検索スコープ。"""

    room_id: str = ""
    account_id: str = ""


__all__ = [
    "EmotionMemory",
    "EmotionTag",
    "EpisodicEntry",
    "EpisodicInput",
    "EpisodicScope",
    "LongTermGoal",
    "SearchHit",
    "SemanticEntry",
    "SemanticInput",
    "SemanticScope",
]
