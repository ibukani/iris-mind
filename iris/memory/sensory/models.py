from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iris.memory.models import ContentBlock


@dataclass
class RawInput:
    block: ContentBlock
    room_id: str = ""
    account_id: str = ""
    session_id: str = ""
    timestamp: str = ""

    def to_dict(self, default_room_id: str = "") -> dict[str, Any]:
        result: dict[str, Any] = {"room_id": self.room_id or default_room_id}
        raw_block = self.block
        result["raw"] = raw_block.get("text", "") if raw_block.get("type") == "text" else ""
        result["raw_block"] = raw_block
        if self.timestamp:
            result["raw_timestamp"] = self.timestamp
        if self.account_id:
            result["account_id"] = self.account_id
        if self.session_id:
            result["session_id"] = self.session_id
        return result


@dataclass
class SensorySnapshot:
    room_id: str
    fragments: list[ContentBlock]
    raw: RawInput | None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"room_id": self.room_id}
        if self.fragments:
            result["fragments"] = list(self.fragments)
            result["fragment"] = "".join(b.get("text", "") for b in self.fragments if b.get("type") == "text")
        if self.raw is not None:
            result.update(self.raw.to_dict(self.room_id))
        return result


@dataclass(frozen=True)
class PendingInputKey:
    account_id: str
    room_id: str


@dataclass
class PendingInputEntry:
    content: str
    account_id: str
    room_id: str
