from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

HOST = "127.0.0.1"
PORT = 9876


class Permission(Enum):
    PERMISSION_SEND_CHAT = "send_chat"
    PERMISSION_RECEIVE_CHAT = "receive_chat"
    PERMISSION_SEND_COMMAND = "send_command"
    PERMISSION_RECEIVE_COMMAND = "receive_command"
    PERMISSION_RECEIVE_LOG = "receive_log"
    PERMISSION_INTERRUPT = "interrupt"
    PERMISSION_EXECUTE_ACTION = "execute_action"
    PERMISSION_SEND_VOICE_INDICATOR = "send_voice_indicator"


class Direction(Enum):
    REQUEST = "request"
    RESPONSE = "response"
    STREAM = "stream"
    EVENT = "event"


class StreamState(StrEnum):
    THINKING = "thinking"
    SPEAKING = "speaking"
    DONE = "done"
    INTERRUPTED = "interrupted"


class SessionState(Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class AuthMessage(BaseModel):
    msg_type: str = "auth"
    access_token: str | None = None
    role: str = "external"
    permissions: list[Permission] = []
    identity: str = ""
    description: str = ""


class ControlMessage(BaseModel):
    msg_type: str
    session_id: str | None = None
    error_message: str | None = None


class Message(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    correlation_id: str | None = None
    session_id: str = ""
    source_role: str = ""
    target_role: str = "*"
    user_identity: str = ""
    direction: Direction
    msg_type: str
    content: str
    content_type: str = "text/plain"
    state: str | None = None
    metadata: dict = Field(default_factory=dict)


class CommandInput(BaseModel):
    msg_type: str = "command"
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    session_id: str = ""
    source_role: str = ""
    content: str


class SystemMessage(BaseModel):
    action: str = ""
    user_id: str = ""
    nickname: str = ""
    text: str = ""


class CommandOutput(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    correlation_id: str | None = None
    session_id: str = ""
    msg_type: str = "command"
    content: str
    state: str | None = None


class PingMessage(BaseModel):
    msg_type: str = "ping"


class PongMessage(BaseModel):
    msg_type: str = "pong"


class SessionInfo(BaseModel):
    session_id: str
    state: SessionState
    role: str = "external"
    permissions: list[Permission] = []
    identity: str = ""
    description: str = ""
    conn: Any | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC))
