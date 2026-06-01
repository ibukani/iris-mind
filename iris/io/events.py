from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from iris.event.base import Event


@dataclass
class SpeakerIdentity:
    provider: str = ""
    subject: str = ""
    provider_name: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class MessageEvent(Event):
    session_id: str = ""
    source_role: str = ""
    target_role: str = ""
    account_id: str = ""
    direction: str = ""
    msg_type: str = ""
    content: str = ""
    state: str | None = None
    correlation_id: str | None = None
    room_id: str = ""
    speaker: SpeakerIdentity | None = None


@dataclass
class ControlMessageEvent(Event):
    action: str = ""
    account_id: str = ""
    room_id: str = ""
    display_name: str = ""
    text: str = ""
    session_id: str = ""
    identity: dict[str, Any] | None = None
    profile: dict[str, str] | None = None
    metadata: dict[str, str] | None = None


@dataclass
class InputReady(Event):
    timestamp: datetime | None = None
    source: str = ""
    session_id: str = ""
    content: str = ""
    account_id: str = ""
    room_id: str = ""
    context: dict | None = None


@dataclass
class InterruptEvent(Event):
    room_id: str = ""


@dataclass
class SessionDisconnectEvent(Event):
    session_id: str = ""
    session_tag: str = ""


__all__ = [
    "ControlMessageEvent",
    "InputReady",
    "InterruptEvent",
    "MessageEvent",
    "SessionDisconnectEvent",
    "SpeakerIdentity",
]
