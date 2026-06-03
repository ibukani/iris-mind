from __future__ import annotations

from typing import Any

from iris.account.models import Provider
from iris.event.base import Event


class AccountCreatedEvent(Event):
    account_id: str = ""
    display_name: str = ""


class AccountUpdatedEvent(Event):
    account_id: str = ""
    field_name: str = ""
    old_value: Any = None
    new_value: Any = None


class AccountIdentityLinkedEvent(Event):
    account_id: str = ""
    provider: Provider = Provider.LOCAL
    subject: str = ""
    provider_name: str = ""
