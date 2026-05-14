from __future__ import annotations

import json as _json
import logging
import multiprocessing.connection as _connection
from typing import Any

from .event import Event

logger = logging.getLogger(__name__)

PIPE_NAME_KERNEL_OUTPUT = r"\\.\pipe\iris-kernel"
PIPE_NAME_KERNEL_INPUT = r"\\.\pipe\iris-kernel-input"
PIPE_NAME_CONTROL = r"\\.\pipe\iris-control"

PIPE_NAME_KERNEL = PIPE_NAME_KERNEL_OUTPUT  # backward compat

_EventTransport = Any  # duck-typed: send(event: Event), recv() -> Event


def _serialize(event: Event) -> bytes:
    return _json.dumps(event.to_dict(), ensure_ascii=False).encode("utf-8")


def _deserialize(data: bytes) -> Event:
    return Event.from_dict(_json.loads(data.decode("utf-8")))


class PipeServer:
    def __init__(self, address: str = PIPE_NAME_KERNEL) -> None:
        self._listener = _connection.Listener(address, family="AF_PIPE")

    def accept(self) -> PipeConnection:
        raw = self._listener.accept()
        logger.info("PipeServer accepted connection from %s", self._listener.address)
        return PipeConnection(raw)

    def close(self) -> None:
        self._listener.close()

    @property
    def address(self) -> Any:  # noqa: ANN401
        return self._listener.address


class PipeClient:
    def __init__(self, address: str = PIPE_NAME_KERNEL) -> None:
        self._conn = _connection.Client(address, family="AF_PIPE")
        logger.info("PipeClient connected to %s", address)

    def send(self, event: Event) -> None:
        self._conn.send_bytes(_serialize(event))

    def recv(self) -> Event:
        return _deserialize(self._conn.recv_bytes())

    def close(self) -> None:
        self._conn.close()


class PipeConnection:
    def __init__(self, raw: _connection.Connection) -> None:
        self._conn = raw

    def send(self, event: Event) -> None:
        self._conn.send_bytes(_serialize(event))

    def recv(self) -> Event:
        return _deserialize(self._conn.recv_bytes())

    def close(self) -> None:
        self._conn.close()

    def fileno(self) -> int:
        return self._conn.fileno()

    def poll(self, timeout: float = 0.0) -> bool:
        return self._conn.poll(timeout)


class ReplayableTransport:
    def __init__(self, transport: _EventTransport, logfile: str) -> None:
        self._transport = transport
        self._logfile = logfile

    def send(self, event: Event) -> None:
        self._log(event.to_dict())
        self._transport.send(event)

    def recv(self) -> Event:
        event = self._transport.recv()
        self._log(event.to_dict())
        return event

    def _log(self, data: dict[str, Any]) -> None:
        try:
            with open(self._logfile, "a", encoding="utf-8") as f:
                f.write(_json.dumps(data, ensure_ascii=False) + "\n")
        except OSError:
            logger.exception("Failed to write replay log: %s", self._logfile)


__all__ = [
    "PipeServer",
    "PipeClient",
    "PipeConnection",
    "ReplayableTransport",
    "PIPE_NAME_KERNEL",
    "PIPE_NAME_CONTROL",
]
