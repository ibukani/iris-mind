from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from iris.memory.models import ContentBlock

MAX_TURN_LENGTH = 500
MAX_CONTEXT_CHARS = 600

TurnRole = str  # "user" | "assistant" | "system" | "thought" | ...


@dataclass(slots=True)
class ShortTermTurn:
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShortTermTurn:
        return cls(
            role=str(data.get("role", "")),
            blocks=list(data.get("blocks", [])),
            timestamp=str(data.get("timestamp", "")),
            consolidated=bool(data.get("consolidated", False)),
            importance=int(data.get("importance", 0)),
            account_id=str(data.get("account_id", "")),
            room_id=str(data.get("room_id", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "blocks": self.blocks,
            "timestamp": self.timestamp,
            "consolidated": self.consolidated,
            "importance": self.importance,
            "account_id": self.account_id,
            "room_id": self.room_id,
        }


@dataclass(slots=True)
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

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update({"relevance": self.relevance, "index": self.index})
        return base


@dataclass(frozen=True, slots=True)
class ShortTermScope:
    """短期記憶の検索 / 取得スコープ。"""

    room_id: str = ""
    account_id: str = ""


@dataclass(frozen=True, slots=True)
class ActiveUser:
    """アクティブな参加者。"""

    account_id: str
    display_name: str


@dataclass(slots=True)
class _HistoryEntry:
    """EmotionStateManager 用の履歴エントリ。"""

    emotion: dict[str, Any]
    mood: dict[str, float]
    relationship: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
