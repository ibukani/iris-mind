from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iris.event.event_types import Event


@dataclass
class AccountCreatedEvent(Event):
    account_id: str = ""
    display_name: str = ""


@dataclass
class AccountUpdatedEvent(Event):
    account_id: str = ""
    field_name: str = ""
    old_value: Any = None
    new_value: Any = None


@dataclass
class AccountIdentityLinkedEvent(Event):
    account_id: str = ""
    provider: str = ""
    subject: str = ""
    provider_name: str = ""
