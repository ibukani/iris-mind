from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

TCP_HOST = "127.0.0.1"
TCP_PORT = 9876

INPUT_MSG_TYPES: frozenset[str] = frozenset({"text", "command", "system"})


class ConnectionMode(Enum):
    INPUT_ONLY = "input_only"
    OUTPUT_ONLY = "output_only"
    BIDIRECTIONAL = "bidirectional"


class SessionState(Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class AuthMessage(BaseModel):
    msg_type: str = "auth"
    access_token: str | None = None
    mode: ConnectionMode = ConnectionMode.BIDIRECTIONAL


class ControlMessage(BaseModel):
    msg_type: str
    session_id: str | None = None
    error_message: str | None = None


class InputMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    session_id: str = ""
    source: str
    msg_type: str = "text"
    content: str
    content_type: str = "text/plain"
    metadata: dict = {}


class OutputMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    session_id: str = ""
    correlation_id: str | None = None
    msg_type: str
    content: str
    content_type: str = "text/plain"
    destinations: list[str] | None = None
    metadata: dict = {}


class PingMessage(BaseModel):
    msg_type: str = "ping"


class PongMessage(BaseModel):
    msg_type: str = "pong"


class SessionInfo(BaseModel):
    session_id: str
    state: SessionState
    mode: ConnectionMode = ConnectionMode.BIDIRECTIONAL
    conn: Any | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    last_activity: datetime = Field(default_factory=datetime.now)
