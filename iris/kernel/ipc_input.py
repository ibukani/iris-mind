from __future__ import annotations

import logging
import threading
from datetime import datetime

from iris.commands.handler import CommandHandler

from .conversation import ConversationService
from .event import AgentResponseEvent, UserInputEvent
from .event_bus import EventBusProtocol
from .ipc import PipeConnection, PipeServer
from .proactive import ProactiveEngine

logger = logging.getLogger(__name__)

PIPE_NAME_INPUT = r"\\.\pipe\iris-kernel-input"


class InputBridge:
    def __init__(self, event_bus: EventBusProtocol, pipe_address: str = PIPE_NAME_INPUT) -> None:
        self._event_bus = event_bus
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
                    target=self._handle_input,
                    args=(conn, conn_id),
                    daemon=True,
                    name=f"input-{conn_id}",
                )
                t.start()
            except Exception:
                if self._running:
                    logger.exception("InputBridge accept failed")
                break

    def _handle_input(self, conn: PipeConnection, conn_id: int) -> None:
        try:
            while self._running:
                event = conn.recv()
                self._event_bus.publish(event)
        except (EOFError, ConnectionError, BrokenPipeError):
            logger.info("InputBridge: connection #%d disconnected", conn_id)


class CommandRouter:
    def __init__(
        self,
        cmd_handler: CommandHandler,
        proactive: ProactiveEngine,
        event_bus: EventBusProtocol,
        conversation: ConversationService,
    ) -> None:
        self._cmd_handler = cmd_handler
        self._proactive = proactive
        self._event_bus = event_bus
        self._conversation = conversation
        self._event_bus.subscribe("UserInputEvent", self._on_user_input)

    def _on_user_input(self, event: UserInputEvent) -> None:
        if event.content.startswith("/"):
            self._proactive.notify_user_activity()
            response = self._cmd_handler.handle(event.content)
            if response:
                self._event_bus.publish(
                    AgentResponseEvent(
                        timestamp=datetime.now(),
                        source="command",
                        content=response,
                        trace_id=event.trace_id,
                    )
                )
        else:
            self._conversation.process_input(event.content)


__all__ = ["InputBridge", "CommandRouter"]
