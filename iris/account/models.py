from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Provider(StrEnum):
    LOCAL = "local"
    DISCORD = "discord"


class ResolvedIdentity(BaseModel):
    """parse_identity の結果。"""

    model_config = ConfigDict(frozen=True)

    provider: Provider | None
    subject: str = ""
    provider_name: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


def parse_identity(identity: dict[str, Any] | None) -> ResolvedIdentity:
    """identity dict を ResolvedIdentity に変換する。"""
    if not identity:
        return ResolvedIdentity(provider=None)
    raw_metadata = identity.get("metadata", {})
    metadata: dict[str, object] = raw_metadata if isinstance(raw_metadata, dict) else {}
    raw_provider = str(identity.get("provider", ""))
    try:
        provider = Provider(raw_provider)
    except ValueError:
        return ResolvedIdentity(provider=None, metadata=metadata)
    return ResolvedIdentity(
        provider=provider,
        subject=str(identity.get("subject", "")),
        provider_name=str(identity.get("provider_name", "")),
        metadata=metadata,
    )


class Account(BaseModel):
    """アカウント情報。"""

    account_id: str = ""
    display_name: str = ""
    created_at: str = ""
    last_seen: str | None = None
    profile: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def set_defaults(self) -> Account:
        if not self.account_id:
            self.account_id = uuid4().hex[:16]
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
        return self


class AccountIdentity(BaseModel):
    """外部IDとアカウントの紐付け。"""

    provider: Provider
    subject: str
    account_id: str
    provider_name: str = ""
    linked_at: str = ""
    last_seen: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def set_defaults(self) -> AccountIdentity:
        if not self.linked_at:
            self.linked_at = datetime.now(UTC).isoformat()
        return self

    @property
    def key(self) -> tuple[str, str]:
        return self.provider.value, self.subject


class ProfileUpdate(BaseModel):
    """アカウントプロフィール更新要求。"""

    model_config = ConfigDict(frozen=True)

    fields: dict[str, object] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.fields
