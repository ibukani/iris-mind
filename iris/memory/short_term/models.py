from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from iris.memory.models import ContentBlock

MAX_TURN_LENGTH = 500
MAX_CONTEXT_CHARS = 600

TurnRole = str  # "user" | "assistant" | "system" | "thought" | ...


class ShortTermTurn(BaseModel):
    """短期記憶の 1 ターン。"""

    role: TurnRole
    blocks: list[ContentBlock]
    timestamp: str = ""
    consolidated: bool = False
    importance: int = 0
    account_id: str = ""
    room_id: str = ""

    @property
    def text(self) -> str:
        from iris.memory.models import blocks_text

        return blocks_text(self.blocks)


class ShortTermSearchResult(ShortTermTurn):
    """短期記憶の検索結果。基底ターンにランキング情報を追加。"""

    relevance: float = 0.0
    index: int = 0

    @classmethod
    def from_turn(
        cls,
        turn: ShortTermTurn,
        *,
        relevance: float,
        index: int,
    ) -> ShortTermSearchResult:
        return cls(
            role=turn.role,
            blocks=turn.blocks,
            timestamp=turn.timestamp,
            consolidated=turn.consolidated,
            importance=turn.importance,
            account_id=turn.account_id,
            room_id=turn.room_id,
            relevance=relevance,
            index=index,
        )


class ShortTermScope(BaseModel):
    """短期記憶の検索 / 取得スコープ。"""

    model_config = {"frozen": True}

    room_id: str = ""
    account_id: str = ""


class ActiveUser(BaseModel):
    """アクティブな参加者。"""

    model_config = {"frozen": True}

    account_id: str
    display_name: str


class _HistoryEntry(BaseModel):
    """EmotionStateManager 用の履歴エントリ。"""

    emotion: dict[str, Any]
    mood: dict[str, float]
    relationship: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
