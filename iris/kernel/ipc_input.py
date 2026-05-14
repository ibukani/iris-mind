from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from .event import AgentResponseEvent, UserInputEvent
from .event_bus import EventBusProtocol
from .ipc import PipeServer

logger = logging.getLogger(__name__)

PIPE_NAME_INPUT = r"\\.\pipe\iris-kernel-input"


class InputBridge:
    def __init__(self, event_bus: EventBusProtocol, pipe_address: str = PIPE_NAME_INPUT) -> None:
        self._event_bus = event_bus
        self._pipe_address = pipe_address
        self._server: PipeServer | None = None

    def start(self) -> None:
        self._server = PipeServer(self._pipe_address)
        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="input-bridge")
        self._thread.start()
        logger.info("InputBridge started on %s", self._pipe_address)

    def stop(self) -> None:
        if self._server is not None:
            self._server.close()
        logger.info("InputBridge stopped")

    def _accept_loop(self) -> None:
        server = self._server
        assert server is not None, "start() must be called before accept"
        try:
            conn = server.accept()
            logger.info("InputBridge: Input Process connected")
            while True:
                event = conn.recv()
                self._event_bus.publish(event)
        except Exception:
            logger.exception("InputBridge: connection lost")


class CommandRouter:
    def __init__(self, cmd_handler: Any, proactive: Any, event_bus: EventBusProtocol) -> None:
        self._cmd_handler = cmd_handler
        self._proactive = proactive
        self._event_bus = event_bus
        self._event_bus.subscribe("UserInputEvent", self._on_user_input)

    def _on_user_input(self, event: UserInputEvent) -> None:
        if not event.content.startswith("/"):
            return
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


__all__ = ["InputBridge", "CommandRouter"]
