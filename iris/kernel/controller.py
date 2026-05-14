from __future__ import annotations

import contextlib
import logging
import subprocess
import sys
import time

from .config import Config
from .factory import KernelContext, KernelFactory
from .ipc import PIPE_NAME_KERNEL_INPUT, PIPE_NAME_KERNEL_OUTPUT
from .ipc_input import InputBridge
from .ipc_output import OutputBridge

logger = logging.getLogger(__name__)

_HEALTH_INTERVAL = 5.0
_MAX_RESTARTS = 10


class IrisController:
    def __init__(self, config: Config, enable_input: bool = True, enable_output: bool = True) -> None:
        self._config = config
        self._enable_input = enable_input
        self._enable_output = enable_output

        self._ctx: KernelContext | None = None
        self._output_bridge: OutputBridge | None = None
        self._input_bridge: InputBridge | None = None
        self._output_proc: subprocess.Popen | None = None
        self._input_proc: subprocess.Popen | None = None
        self._restart_count: int = 0
        self._running = False

    def launch(self) -> None:
        logger.info("IrisController: launching Iris")

        self._ctx = KernelFactory.build(self._config)

        if self._enable_output:
            self._output_bridge = OutputBridge(self._ctx.event_bus, PIPE_NAME_KERNEL_OUTPUT)
            self._output_bridge.start()

        if self._enable_input:
            self._input_bridge = InputBridge(self._ctx.event_bus, PIPE_NAME_KERNEL_INPUT)
            self._input_bridge.start()

        time.sleep(0.3)

        if self._enable_output:
            self._output_proc = subprocess.Popen(
                [sys.executable, "-m", "adapters.cli.output_main", PIPE_NAME_KERNEL_OUTPUT],
            )
        if self._enable_input:
            self._input_proc = subprocess.Popen(
                [sys.executable, "-m", "adapters.cli.input_main", PIPE_NAME_KERNEL_INPUT],
            )

        self._running = True
        logger.info("IrisController: all processes launched")

        try:
            while self._running:
                time.sleep(_HEALTH_INTERVAL)
                self._check_health()
        except KeyboardInterrupt:
            logger.info("IrisController: KeyboardInterrupt received")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self._running = False
        logger.info("IrisController: shutting down")

        self._terminate_proc(self._output_proc)
        self._terminate_proc(self._input_proc)

        if self._output_bridge is not None:
            self._output_bridge.stop()
        if self._input_bridge is not None:
            self._input_bridge.stop()

        ctx = self._ctx
        if ctx is not None:
            with contextlib.suppress(Exception):
                ctx.conversation.session_reflect()
            ctx.kernel.shutdown()

        logger.info("IrisController: shutdown complete")

    def _check_health(self) -> None:
        if self._output_proc is not None and self._output_proc.poll() is not None:
            logger.warning("Output Process died (code %s), restarting", self._output_proc.returncode)
            self._output_proc = self._spawn_output()

        if self._input_proc is not None and self._input_proc.poll() is not None:
            logger.warning("Input Process died (code %s), restarting", self._input_proc.returncode)
            self._input_proc = self._spawn_input()

    def _spawn_output(self) -> subprocess.Popen | None:
        return self._spawn_safe([sys.executable, "-m", "adapters.cli.output_main", PIPE_NAME_KERNEL_OUTPUT])

    def _spawn_input(self) -> subprocess.Popen | None:
        return self._spawn_safe([sys.executable, "-m", "adapters.cli.input_main", PIPE_NAME_KERNEL_INPUT])

    def _spawn_safe(self, cmd: list[str]) -> subprocess.Popen | None:
        self._restart_count += 1
        if self._restart_count > _MAX_RESTARTS:
            logger.error("Too many restarts (%d), giving up", self._restart_count)
            return None
        try:
            proc = subprocess.Popen(cmd)
            time.sleep(0.5)
            return proc
        except OSError as e:
            logger.exception("Failed to spawn %s: %s", cmd[0], e)
            return None

    @staticmethod
    def _terminate_proc(proc: subprocess.Popen | None) -> None:
        if proc is None:
            return
        with contextlib.suppress(Exception):
            proc.terminate()
            proc.wait(timeout=3)
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2)


__all__ = ["IrisController"]
