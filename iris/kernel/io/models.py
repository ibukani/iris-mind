from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

PIPE_NAME_INPUT = r"\\.\pipe\iris-kernel-input"
PIPE_NAME_OUTPUT = r"\\.\pipe\iris-kernel-output"


class InputMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    source: str
    msg_type: str = "text"
    content: str
    content_type: str = "text/plain"
    metadata: dict = {}


class OutputMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    correlation_id: str | None = None
    msg_type: str
    content: str
    content_type: str = "text/plain"
    destinations: list[str] | None = None
    metadata: dict = {}
