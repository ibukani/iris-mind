from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4


@dataclass
class Account:
    """アカウント情報。"""

    account_id: str = ""
    nickname: str = ""
    created_at: str = ""
    last_seen: str | None = None
    profile: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.account_id:
            self.account_id = uuid4().hex[:16]
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, object]:
        return {
            "account_id": self.account_id,
            "nickname": self.nickname,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
            "profile": self.profile,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Account:
        last_seen: str | None = None
        if isinstance(data.get("last_seen"), str):
            last_seen = cast(str, data["last_seen"])
        raw_profile = data.get("profile", {})
        profile: dict[str, object] = {}
        if isinstance(raw_profile, dict):
            profile = cast("dict[str, object]", raw_profile)
        return cls(
            account_id=str(data.get("account_id", "")),
            nickname=str(data.get("nickname", "")),
            created_at=str(data.get("created_at", "")),
            last_seen=last_seen,
            profile=profile,
        )


@dataclass
class AccountIdentity:
    """外部IDとアカウントの紐付け。"""

    provider: str
    subject: str
    account_id: str
    display_name: str = ""
    linked_at: str = ""
    last_seen: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.linked_at:
            self.linked_at = datetime.now(UTC).isoformat()

    @property
    def key(self) -> tuple[str, str]:
        return self.provider, self.subject

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "subject": self.subject,
            "account_id": self.account_id,
            "display_name": self.display_name,
            "linked_at": self.linked_at,
            "last_seen": self.last_seen,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AccountIdentity:
        last_seen: str | None = None
        if isinstance(data.get("last_seen"), str):
            last_seen = cast(str, data["last_seen"])
        raw_metadata = data.get("metadata", {})
        metadata: dict[str, object] = {}
        if isinstance(raw_metadata, dict):
            metadata = cast("dict[str, object]", raw_metadata)
        return cls(
            provider=str(data.get("provider", "")),
            subject=str(data.get("subject", "")),
            account_id=str(data.get("account_id", "")),
            display_name=str(data.get("display_name", "")),
            linked_at=str(data.get("linked_at", "")),
            last_seen=last_seen,
            metadata=metadata,
        )


@dataclass
class SessionBinding:
    """セッション ↔ アカウントの紐付け。"""

    session_id: str
    account_id: str
    connected_at: str = ""
    disconnected_at: str | None = None

    def __post_init__(self) -> None:
        if not self.connected_at:
            self.connected_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "account_id": self.account_id,
            "connected_at": self.connected_at,
            "disconnected_at": self.disconnected_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SessionBinding:
        disconnected_at: str | None = None
        if isinstance(data.get("disconnected_at"), str):
            disconnected_at = cast(str, data["disconnected_at"])
        return cls(
            session_id=str(data.get("session_id", "")),
            account_id=str(data.get("account_id", "")),
            connected_at=str(data.get("connected_at", "")),
            disconnected_at=disconnected_at,
        )
