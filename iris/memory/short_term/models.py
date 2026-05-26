from __future__ import annotations

from typing import TypedDict

MAX_TURN_LENGTH = 500
MAX_CONTEXT_CHARS = 600


class TurnData(TypedDict):
    role: str
    content: str
    timestamp: str
    consolidated: bool
    importance: int
    user_identity: str


class SearchResult(TurnData, total=False):
    relevance: float
    index: int
