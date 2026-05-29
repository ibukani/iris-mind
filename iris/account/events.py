from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iris.event.event_types import Event


@dataclass
class AccountCreatedEvent(Event):
    account_id: str = ""
    nickname: str = ""
    discord_id: str | None = None


@dataclass
class AccountUpdatedEvent(Event):
    account_id: str = ""
    field_name: str = ""
    old_value: Any = None
    new_value: Any = None


@dataclass
class AccountSessionBoundEvent(Event):
    session_id: str = ""
    account_id: str = ""


@dataclass
class AccountSessionUnboundEvent(Event):
    session_id: str = ""
    account_id: str = ""
