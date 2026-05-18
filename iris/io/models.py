from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

TCP_HOST = "127.0.0.1"
TCP_PORT = 9876

INPUT_MSG_TYPES: frozenset[str] = frozenset({"dispatch_text", "converse_text", "command", "system"})
OUTPUT_STREAM_STATES: frozenset[str] = frozenset({"thinking", "speaking", "done", "interrupted"})


class ConnectionMode(Enum):
    INPUT_ONLY = "input_only"
    OUTPUT_ONLY = "output_only"
    BIDIRECTIONAL = "bidirectional"


class SessionState(Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class SessionRole(Enum):
    CONVERSATION_INPUT = "conversation_input"
    COMMAND_INPUT = "command_input"
    CONVERSATION_OUTPUT = "conversation_output"
    COMMAND_OUTPUT = "command_output"
    LOG = "log"


class AuthMessage(BaseModel):
    msg_type: str = "auth"
    access_token: str | None = None
    mode: ConnectionMode = ConnectionMode.BIDIRECTIONAL
    roles: list[SessionRole] = [
        SessionRole.CONVERSATION_INPUT,
        SessionRole.CONVERSATION_OUTPUT,
        SessionRole.COMMAND_INPUT,
        SessionRole.COMMAND_OUTPUT,
    ]
    identity: str = ""
    description: str = ""


class ControlMessage(BaseModel):
    msg_type: str
    session_id: str | None = None
    error_message: str | None = None


class InputMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    session_id: str = ""
    source: str
    msg_type: str = "dispatch_text"
    content: str
    content_type: str = "text/plain"
    is_final: bool = True
    metadata: dict = {}


class OutputMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    correlation_id: str | None = None
    msg_type: str
    content: str
    content_type: str = "text/plain"
    state: str | None = None
    metadata: dict = {}


class InterruptMessage(BaseModel):
    msg_type: str = "interrupt"
    session_id: str


class PingMessage(BaseModel):
    msg_type: str = "ping"


class PongMessage(BaseModel):
    msg_type: str = "pong"


class SessionInfo(BaseModel):
    session_id: str
    state: SessionState
    mode: ConnectionMode = ConnectionMode.BIDIRECTIONAL
    roles: list[SessionRole] = []
    identity: str = ""
    description: str = ""
    conn: Any | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    last_activity: datetime = Field(default_factory=datetime.now)
