from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field

Direction = Literal["inbound", "outbound", "system"]
Role = Literal["user", "assistant", "system", "tool"]


class ConversationRecord(BaseModel):
    """Raw conversation archive の 1 レコード。

    すべての属性は後から再パース・再生できるよう必須項目を明示する。
    LangMem 抽出のソースレコードを兼ねるため ``id`` と ``timestamp`` は必須。
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    direction: Direction = "inbound"
    role: Role = "user"
    content: str = ""
    room_id: str = ""
    account_id: str = ""
    session_id: str = ""
    source: str = ""
    message_type: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")


__all__ = ["ConversationRecord", "Direction", "Role"]
