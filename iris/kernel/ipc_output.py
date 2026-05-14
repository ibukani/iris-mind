from __future__ import annotations

import logging
import threading

from .event import (
    Event,
)
from .event_bus import EventBusProtocol
from .ipc import PipeConnection, PipeServer

logger = logging.getLogger(__name__)

_DISPLAY_EVENTS = {
    "AgentStreamEvent",
    "AgentResponseEvent",
    "ProactiveSpeechEvent",
    "AgentAnomalyEvent",
}


class OutputBridge:
    """Kernel 側: EventBus の表示イベントを購読し、Pipe 経由で Output Process に中継する。"""

    def __init__(self, event_bus: EventBusProtocol, pipe_address: str) -> None:
        self._event_bus = event_bus
        self._pipe_address = pipe_address
        self._output_conn: PipeConnection | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """PipeServer を開始し、購読を登録する。"""
        self._server = PipeServer(self._pipe_address)
        self._subscribe()
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True, name="output-bridge-accept")
        self._accept_thread.start()
        logger.info("OutputBridge started on %s", self._pipe_address)

    def stop(self) -> None:
        """購読解除と PipeServer の停止。"""
        self._unsubscribe()
        if self._server is not None:
            self._server.close()
        logger.info("OutputBridge stopped")

    def _subscribe(self) -> None:
        for evt_type in _DISPLAY_EVENTS:
            self._event_bus.subscribe(evt_type, self._send)

    def _unsubscribe(self) -> None:
        for evt_type in _DISPLAY_EVENTS:
            self._event_bus.unsubscribe(evt_type, self._send)

    def _accept_loop(self) -> None:
        try:
            conn = self._server.accept()
            logger.info("OutputBridge: Output Process connected")
            with self._lock:
                self._output_conn = conn
        except Exception:
            logger.exception("OutputBridge accept failed")

    def _send(self, event: Event) -> None:
        with self._lock:
            conn = self._output_conn
        if conn is None:
            return
        try:
            conn.send(event)
        except (BrokenPipeError, ConnectionError, EOFError):
            logger.warning("OutputBridge: connection lost")
            with self._lock:
                self._output_conn = None


__all__ = ["OutputBridge"]
