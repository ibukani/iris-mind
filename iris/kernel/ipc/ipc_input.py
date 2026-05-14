from __future__ import annotations

import logging
import threading
from datetime import datetime

from iris.commands.handler import CommandHandler

from ..event.event import CommandRequestEvent, CommandResponseEvent, Event
from ..event.event_bus import EventBusProtocol
from .ipc import PipeConnection, PipeServer

logger = logging.getLogger(__name__)

PIPE_NAME_INPUT = r"\\.\pipe\iris-kernel-input"


class InputBridge:
    def __init__(
        self,
        event_bus: EventBusProtocol,
        cmd_handler: CommandHandler,
        pipe_address: str = PIPE_NAME_INPUT,
    ) -> None:
        self._event_bus = event_bus
        self._cmd_handler = cmd_handler
        self._pipe_address = pipe_address
        self._server: PipeServer | None = None
        self._running = False
        self._lock = threading.Lock()
        self._conn_count = 0

    def start(self) -> None:
        self._server = PipeServer(self._pipe_address)
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="input-bridge")
        self._thread.start()
        logger.info("InputBridge started on %s", self._pipe_address)

    def stop(self) -> None:
        self._running = False
        if self._server is not None:
            self._server.close()
        logger.info("InputBridge stopped (%d connections handled)", self._conn_count)

    def _accept_loop(self) -> None:
        server = self._server
        assert server is not None, "start() must be called before accept"
        while self._running:
            try:
                conn = server.accept()
                with self._lock:
                    self._conn_count += 1
                conn_id = self._conn_count
                logger.info("InputBridge: Input connection #%d accepted", conn_id)
                t = threading.Thread(
                    target=self._serve_connection,
                    args=(conn, conn_id),
                    daemon=True,
                    name=f"input-{conn_id}",
                )
                t.start()
            except Exception:
                if self._running:
                    logger.exception("InputBridge accept failed")
                break

    def _serve_connection(self, conn: PipeConnection, conn_id: int) -> None:
        try:
            while self._running:
                self._route_event(conn, conn.recv())
        except (EOFError, ConnectionError, BrokenPipeError):
            logger.info("InputBridge: connection #%d disconnected", conn_id)

    def _route_event(self, conn: PipeConnection, event: Event) -> None:
        match event:
            case CommandRequestEvent():
                self._exec_command(conn, event)
            case _:
                self._event_bus.publish(event)

    def _exec_command(self, conn: PipeConnection, event: CommandRequestEvent) -> None:
        response = self._cmd_handler.handle(event.command_name, event.args)
        conn.send(
            CommandResponseEvent(
                timestamp=datetime.now(),
                source="command",
                command_name=event.command_name,
                content=response,
                trace_id=event.trace_id,
            ),
        )


__all__ = ["InputBridge"]
