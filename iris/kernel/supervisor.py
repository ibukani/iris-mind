from __future__ import annotations

from collections.abc import Callable
import signal
import sys
import threading
import time

from loguru import logger

from iris.kernel.config import Config
from iris.kernel.process import KernelProcessProtocol


class Supervisor:
    """Kernel プロセスのライフサイクルを管理し、管理コンソールを提供する。"""

    def __init__(self, config: Config, debug: bool = False) -> None:
        self._config = config
        self._debug = debug
        self._kernel: KernelProcessProtocol | None = None
        self._shutdown_requested = False
        self._cmd_handler: Callable[[str, str], str] | None = None

    def set_cmd_handler(self, handler: Callable[[str, str], str]) -> None:
        self._cmd_handler = handler

    def run(self) -> None:
        self.start()
        self.wait()

    def start(self) -> None:
        from iris.kernel.process import KernelProcess

        kernel = KernelProcess(self._config, debug=self._debug)
        self._kernel = kernel
        kernel.start()

        # Wire up cmd_handler for mgmt-console command routing
        handler = getattr(kernel, "cmd_handler", None)
        if handler is not None and hasattr(handler, "handle"):
            self._cmd_handler = handler.handle

        signal.signal(signal.SIGINT, self._on_signal)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._on_signal)

        logger.info("Supervisor: running")

    def wait(self) -> None:
        console_thread = threading.Thread(target=self._console_loop, daemon=True, name="mgmt-console")
        console_thread.start()

        try:
            while not self._shutdown_requested:
                if self._kernel is not None and self._kernel.shutdown_requested:
                    logger.info("Supervisor: shutdown requested via command")
                    self._shutdown_requested = True
                    self.shutdown()
                    return
                time.sleep(1)
        except KeyboardInterrupt:
            if not self._shutdown_requested:
                self.shutdown()

    def shutdown(self) -> None:
        logger.info("Supervisor: shutting down")
        if self._kernel is not None:
            self._kernel.shutdown()
        logger.info("Supervisor: shutdown complete")

    def _console_loop(self) -> None:
        while not self._shutdown_requested:
            line = self._read_line()
            if line is None:
                break
            if not line:
                continue
            if self._execute_line(line):
                break

    def _read_line(self) -> str | None:
        sys.stdout.write("> ")
        sys.stdout.flush()
        try:
            text = sys.stdin.readline()
        except (EOFError, KeyboardInterrupt):
            return None
        if not text:
            return None
        return text.strip()

    def _execute_line(self, line: str) -> bool:
        if line.lower() in ("exit", "quit"):
            self._shutdown_requested = True
            self.shutdown()
            return True
        if not line.startswith("/"):
            print("Type /help for available commands")
            return False
        parts = line[1:].strip().split(maxsplit=1)
        name = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""
        if self._cmd_handler is not None:
            print(self._cmd_handler(name, args))
            if name == "shutdown":
                return True
        else:
            print(f"Unknown command: /{name}")
        return False

    def _on_signal(self, sig: int, _frame: object) -> None:
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        logger.info("Supervisor: received signal {}, starting shutdown", sig)
        self.shutdown()
        sys.exit(0)
