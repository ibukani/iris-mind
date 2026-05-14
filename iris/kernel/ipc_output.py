from __future__ import annotations

import contextlib
import logging
import threading

from .event import Event
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
    def __init__(self, event_bus: EventBusProtocol, pipe_address: str) -> None:
        self._event_bus = event_bus
        self._pipe_address = pipe_address
        self._output_conn: PipeConnection | None = None
        self._lock = threading.Lock()
        self._server: PipeServer | None = None
        self._running = False

    def start(self) -> None:
        self._server = PipeServer(self._pipe_address)
        self._subscribe()
        self._running = True
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True, name="output-bridge")
        self._accept_thread.start()
        logger.info("OutputBridge started on %s", self._pipe_address)

    def stop(self) -> None:
        self._running = False
        with self._lock:
            self._output_conn = None
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
        server = self._server
        assert server is not None, "start() must be called before accept"
        while self._running:
            try:
                conn = server.accept()
                logger.info("OutputBridge: Output Process connected")
                with self._lock:
                    old = self._output_conn
                    if old is not None:
                        with contextlib.suppress(Exception):
                            old.close()
                    self._output_conn = conn
            except Exception:
                if self._running:
                    logger.exception("OutputBridge accept failed")
                break

    def _send(self, event: Event) -> None:
        conn: PipeConnection | None
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
