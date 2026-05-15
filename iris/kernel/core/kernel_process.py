from __future__ import annotations

import contextlib
import logging
from typing import Protocol

from iris.kernel.io.input_manager import InputManager
from iris.kernel.io.models import PIPE_NAME_INPUT, PIPE_NAME_OUTPUT, InputMessage, OutputMessage

from ..config import Config
from .factory import KernelContext, KernelFactory

logger = logging.getLogger(__name__)


class KernelProcessProtocol(Protocol):
    def start(self) -> None: ...
    def shutdown(self) -> None: ...


class KernelProcess:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._ctx: KernelContext | None = None
        self._input_mgr: InputManager | None = None

    def start(self) -> None:
        logger.info("KernelProcess: starting")

        self._ctx = KernelFactory.build(self._config)

        self._ctx.output.start(PIPE_NAME_OUTPUT)

        self._input_mgr = InputManager(on_input=self._on_input, pipe_address=PIPE_NAME_INPUT)
        self._input_mgr.start()

        logger.info("KernelProcess: started")

    def _on_input(self, msg: InputMessage) -> None:
        ctx = self._ctx
        assert ctx is not None

        if msg.msg_type == "command":
            cmd = msg.content[1:].strip().split(maxsplit=1)
            name = cmd[0].lower() if cmd else ""
            args = cmd[1] if len(cmd) > 1 else ""
            result = ctx.cmd_handler.handle(name, args)
            ctx.output.send(OutputMessage(msg_type="command", content=result))
            return

        ctx.kernel.on_input(msg)
        ctx.conversation.process_input(
            msg.content,
            on_complete=lambda text: ctx.kernel.on_response_complete(text),
        )

    def shutdown(self) -> None:
        logger.info("KernelProcess: shutting down")

        if self._input_mgr is not None:
            self._input_mgr.stop()

        ctx = self._ctx
        if ctx is not None:
            with contextlib.suppress(Exception):
                ctx.conversation.session_reflect()
            with contextlib.suppress(Exception):
                ctx.output.stop()
            ctx.kernel.shutdown()

        logger.info("KernelProcess: shutdown complete")
