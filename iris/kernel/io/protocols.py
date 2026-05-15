from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from iris.kernel.io.models import InputMessage, OutputMessage


@runtime_checkable
class InputDriver(Protocol):
    driver_id: str
    description: str

    def start(self, handler: Callable[[InputMessage], None]) -> None: ...
    def stop(self) -> None: ...


@runtime_checkable
class OutputDriver(Protocol):
    driver_id: str
    description: str
    features: set[str]  # e.g. {"stream", "text", "rich"}

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def write(self, message: OutputMessage) -> None: ...
    def can_handle(self, destination: str) -> bool: ...
