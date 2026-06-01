from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from iris.memory.models import ContentBlock

MAX_TURN_LENGTH = 500
MAX_CONTEXT_CHARS = 600


class ShortTermTurn(TypedDict, total=False):
    role: str
    blocks: list[ContentBlock]
    timestamp: str
    consolidated: bool
    importance: int
    account_id: str
    room_id: str


class ShortTermSearchResult(ShortTermTurn, total=False):
    relevance: float
    index: int


class ShortTermScope(TypedDict, total=False):
    room_id: str
    account_id: str


@dataclass(frozen=True, slots=True)
class ActiveUser:
    """アクティブな参加者。"""

    account_id: str
    display_name: str
