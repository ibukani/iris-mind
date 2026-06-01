from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from iris.event.base import Event


class SpeakerIdentity(BaseModel):
    provider: str = ""
    subject: str = ""
    provider_name: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


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


class InputReady(Event):
    session_id: str = ""
    content: str = ""
    account_id: str = ""
    room_id: str = ""
    context: dict | None = None


class InterruptEvent(Event):
    room_id: str = ""


class SessionDisconnectEvent(Event):
    session_id: str = ""
    session_tag: str = ""


class InhibitionRequestEvent(Event):
    """クライアントからの抑制制御信号。

    IO 層が gRPC の `Message(msg_type="inhibition", content="reason:action[:duration]")`
    を受信したとき、内部表現として型付きイベントに変換して publish する。
    action フィールドは文字列で受け取り、handler 側で Boolean 風表記
    ("true" / "false" / "suppress" / "unsuppress" / "hyperdirect") に解決する。
    """

    action: str = "suppress"
    reason: str = ""
    duration: float = 0.0
    room_id: str = ""
    session_id: str = ""


__all__ = [
    "ControlMessageEvent",
    "InhibitionRequestEvent",
    "InputReady",
    "InterruptEvent",
    "MessageEvent",
    "SessionDisconnectEvent",
    "SpeakerIdentity",
]
