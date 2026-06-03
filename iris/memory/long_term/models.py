from __future__ import annotations

import time
from typing import Any
import uuid

from pydantic import BaseModel, Field, model_serializer


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


class EpisodicEntry(BaseModel):
    """エピソード記憶 1 件分の構造化データ。"""

    summary: str
    timestamp: str
    room_id: str = ""
    account_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticEntry(BaseModel):
    """意味記憶 1 件分の構造化データ。"""

    content: str
    id: str = ""
    type: str = "lesson"
    tags: list[str] = Field(default_factory=list)
    timestamp: str = ""
    room_id: str = ""
    account_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class EpisodicInput(BaseModel):
    """エピソード記憶への保存入力。"""

    content: str
    kind: str = ""
    metadata: dict[str, Any] | None = None
    room_id: str = ""
    account_id: str = ""


class SemanticInput(BaseModel):
    """意味記憶への保存入力。"""

    content: str
    type: str = "lesson"
    tags: list[str] = Field(default_factory=list)
    room_id: str = ""
    account_id: str = ""


class SearchHit(BaseModel):
    """意味検索・vector 検索の共通結果型。"""

    content: str
    type: str = "unknown"
    tags: list[str] = Field(default_factory=list)
    score: float = 0.0
    timestamp: str = ""
    id: str = ""
    room_id: str = ""
    account_id: str = ""


class EmotionTag(BaseModel):
    """エピソード記憶に紐づく感情タグ。"""

    emotion: dict[str, float] = Field(default_factory=dict)
    intensity: float = 0.0
    type: str = "emotion_tag"


class EmotionMemory(BaseModel):
    """search_emotional() の戻り値型。"""

    entry: EpisodicEntry
    score: float = 0.0
    intensity: float = 0.0

    @model_serializer(mode="wrap")
    def serialize_model(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        entry_data = data.pop("entry")
        return {**entry_data, "score": round(self.score, 4), "intensity": self.intensity}


class EpisodicScope(BaseModel):
    """エピソード記憶の検索スコープ。"""

    model_config = {"frozen": True}

    room_id: str = ""
    account_id: str = ""


class SemanticScope(BaseModel):
    """意味記憶の検索スコープ。"""

    model_config = {"frozen": True}

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
