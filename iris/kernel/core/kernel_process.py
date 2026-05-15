from __future__ import annotations

import contextlib
import logging
from typing import Protocol

from ..config import Config
from .factory import KernelContext, KernelFactory

logger = logging.getLogger(__name__)


class KernelProcessProtocol(Protocol):
    def start(self) -> None: ...
    def shutdown(self) -> None: ...

    @property
    def shutdown_requested(self) -> bool: ...


class KernelProcess:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._ctx: KernelContext | None = None

    @property
    def shutdown_requested(self) -> bool:
        return self._ctx is not None and self._ctx.shutdown_requested

    def start(self) -> None:
        logger.info("KernelProcess: starting")

        self._ctx = KernelFactory.build(self._config)

        self._ctx.control_mgr.start()
        self._ctx.input_mgr.start()
        self._ctx.output.start()

        logger.info("KernelProcess: started")

    def shutdown(self) -> None:
        logger.info("KernelProcess: shutting down")

        ctx = self._ctx
        if ctx is None:
            logger.info("KernelProcess: shutdown complete (was not started)")
            return

        ctx.input_mgr.stop()
        ctx.output.stop()
        ctx.control_mgr.stop()
        with contextlib.suppress(Exception):
            ctx.conversation.session_reflect()
        ctx.kernel.shutdown()

        logger.info("KernelProcess: shutdown complete")
