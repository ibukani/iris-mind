from __future__ import annotations

import logging
import signal
import sys
import threading
import time

from iris.kernel.config import Config
from iris.kernel.process import KernelProcessProtocol

logger = logging.getLogger(__name__)


class Supervisor:
    """Kernel プロセスのライフサイクルを管理し、管理コンソールを提供する。"""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._kernel: KernelProcessProtocol | None = None
        self._shutdown_requested = False

    def run(self) -> None:
        self.start()
        self.wait()

    def start(self) -> None:
        from iris.kernel.process import KernelProcess

        self._kernel = KernelProcess(self._config)
        self._kernel.start()

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
            sys.stdout.write("> ")
            sys.stdout.flush()
            try:
                text = sys.stdin.readline()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            text = text.rstrip("\r\n")
            if not text.strip():
                continue
            line = text.strip()
            if line.lower() in ("exit", "quit"):
                self._shutdown_requested = True
                self.shutdown()
                break
            if line.startswith("/"):
                parts = line[1:].strip().split(maxsplit=1)
                name = parts[0].lower() if parts else ""
                if name == "shutdown":
                    self._cmd_shutdown()
                    break
                if name == "status":
                    self._cmd_status()
                elif name == "help":
                    self._cmd_help()
                else:
                    print(f"Unknown command: /{name}")
            else:
                print("Type /help for available commands")

    def _cmd_help(self) -> None:
        print("Available commands:")
        print("  /help               Show this help")
        print("  /status             Show kernel status")
        print("  /shutdown           Graceful shutdown")
        print("  exit, quit          Stop supervisor")
        print()
        print("Full kernel command set is available via Named Pipe.")

    def _cmd_status(self) -> None:
        if self._kernel is None:
            print("Kernel: not started")
            return
        state = "running" if not self._kernel.shutdown_requested else "shutdown requested"
        print(f"Kernel: {state}")

    def _cmd_shutdown(self) -> None:
        self._shutdown_requested = True
        self.shutdown()

    def _on_signal(self, sig: int, _frame: object) -> None:
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        logger.info("Supervisor: received signal %d, starting shutdown", sig)
        self.shutdown()
        sys.exit(0)
