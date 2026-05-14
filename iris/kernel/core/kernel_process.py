from __future__ import annotations

import contextlib
import logging
from typing import Protocol

from ..config import Config
from ..ipc.ipc import PIPE_NAME_KERNEL_INPUT, PIPE_NAME_KERNEL_OUTPUT
from ..ipc.ipc_input import InputBridge
from ..ipc.ipc_output import OutputBridge
from .factory import KernelContext, KernelFactory

logger = logging.getLogger(__name__)


class KernelProcessProtocol(Protocol):
    """Supervisor が KernelProcess に要求するインターフェース。"""

    def start(self) -> None: ...
    def shutdown(self) -> None: ...
    def stop_bridge(self, side: str) -> None: ...


class KernelProcess:
    """Iris Kernel プロセス。

    子プロセスの管理は行わず、自身の Bridge スレッド起動とシャットダウンのみ責務を持つ。
    プロセス管理は Supervisor (main.py) が担当する。
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._ctx: KernelContext | None = None
        self._output_bridge: OutputBridge | None = None
        self._input_bridge: InputBridge | None = None

    def start(self) -> None:
        """Kernel を起動する：Factory build → Bridge スレッド開始。"""
        logger.info("KernelProcess: starting")

        self._ctx = KernelFactory.build(self._config)

        self._output_bridge = OutputBridge(self._ctx.event_bus, PIPE_NAME_KERNEL_OUTPUT)
        self._output_bridge.start()

        self._input_bridge = InputBridge(self._ctx.event_bus, PIPE_NAME_KERNEL_INPUT)
        self._input_bridge.start()

        logger.info("KernelProcess: started")

    def shutdown(self) -> None:
        """Kernel をシャットダウンする。"""
        logger.info("KernelProcess: shutting down")

        if self._output_bridge is not None:
            self._output_bridge.stop()
        if self._input_bridge is not None:
            self._input_bridge.stop()

        ctx = self._ctx
        if ctx is not None:
            with contextlib.suppress(Exception):
                ctx.conversation.session_reflect()
            ctx.kernel.shutdown()

        logger.info("KernelProcess: shutdown complete")

    def stop_bridge(self, side: str) -> None:
        """指定 side の Bridge を停止する。"""
        if side == "output" and self._output_bridge is not None:
            self._output_bridge.stop()
            logger.info("KernelProcess: stopped output bridge")
        elif side == "input" and self._input_bridge is not None:
            self._input_bridge.stop()
            logger.info("KernelProcess: stopped input bridge")
        else:
            logger.warning("KernelProcess: unknown bridge side %r", side)


__all__ = ["KernelProcess", "KernelProcessProtocol"]
