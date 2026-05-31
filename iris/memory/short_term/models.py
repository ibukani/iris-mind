from __future__ import annotations

from typing import TypedDict

from iris.memory.models import ContentBlock

MAX_TURN_LENGTH = 500
MAX_CONTEXT_CHARS = 600


class TurnData(TypedDict, total=False):
    role: str
    blocks: list[ContentBlock]
    timestamp: str
    consolidated: bool
    importance: int
    account_id: str
    room_id: str


class SearchResult(TurnData, total=False):
    relevance: float
    index: int
