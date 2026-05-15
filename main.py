#!/usr/bin/env python3
"""Iris Supervisor — プロセス起動・監視・シャットダウンを担当するエントリポイント。

起動方法:
    python main.py                          # Kernel のみ（デフォルト）
    python main.py --input --output         # Kernel + Input + Output（開発用）
    python main.py --input                  # Kernel + Input
    python main.py --output                 # Kernel + Output
    python main.py --verbose                # Kernel 診断ログを stderr に出力
"""

from __future__ import annotations

import argparse
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path

from iris.kernel.config import Config
from iris.kernel.core import KernelProcessProtocol

logger = logging.getLogger(__name__)

_SHUTDOWN_TIMEOUT = 5.0


class Supervisor:
    """子プロセス（Input/Output）のライフサイクルを管理する。"""

    def __init__(self, config: Config, *, spawn_input: bool, spawn_output: bool) -> None:
        self._config = config
        self._spawn_input = spawn_input
        self._spawn_output = spawn_output
        self._kernel: KernelProcessProtocol | None = None
        self._input_proc: subprocess.Popen | None = None
        self._output_proc: subprocess.Popen | None = None
        self._shutdown_requested = False

    def start(self) -> None:
        from iris.kernel.core import KernelProcess

        self._kernel = KernelProcess(self._config)
        self._kernel.start()

        if self._spawn_input:
            from iris.kernel.io.models import PIPE_NAME_INPUT

            self._input_proc = self._spawn(["-m", "adapters.cli.input_main", PIPE_NAME_INPUT], "Input Process")
        if self._spawn_output:
            from iris.kernel.io.models import PIPE_NAME_OUTPUT

            self._output_proc = self._spawn(["-m", "adapters.cli.output_main", PIPE_NAME_OUTPUT], "Output Process")

        signal.signal(signal.SIGINT, self._on_signal)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._on_signal)

        logger.info("Supervisor: running")

    def wait(self) -> None:
        try:
            while not self._shutdown_requested:
                time.sleep(1)
        except KeyboardInterrupt:
            if not self._shutdown_requested:
                self.shutdown()

    def shutdown(self) -> None:
        logger.info("Supervisor: shutting down all processes")
        if self._input_proc is not None:
            self._terminate(self._input_proc, "Input Process")
        if self._kernel is not None:
            self._kernel.shutdown()
        if self._output_proc is not None:
            time.sleep(0.5)
            self._terminate(self._output_proc, "Output Process")
        logger.info("Supervisor: all processes terminated")

    def _spawn(self, python_args: list[str], name: str) -> subprocess.Popen:
        proc = subprocess.Popen(
            [sys.executable] + python_args,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        logger.info("Supervisor: spawned %s (pid=%d)", name, proc.pid)
        return proc

    def _terminate(self, proc: subprocess.Popen, name: str) -> None:
        try:
            proc.terminate()
            proc.wait(timeout=_SHUTDOWN_TIMEOUT)
            logger.info("Supervisor: %s terminated gracefully", name)
        except subprocess.TimeoutExpired:
            logger.warning("Supervisor: %s did not exit in %.1fs, killing", name, _SHUTDOWN_TIMEOUT)
            proc.kill()
            proc.wait(timeout=2)

    def _on_signal(self, sig: int, _frame: object) -> None:
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        logger.info("Supervisor: received signal %d, starting shutdown", sig)
        self.shutdown()
        sys.exit(0)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Iris Supervisor")
    parser.add_argument("--verbose", action="store_true", help="Kernel 診断ログを stderr に出力")
    parser.add_argument("--input", action="store_true", help="Input 子プロセスも起動")
    parser.add_argument("--output", action="store_true", help="Output 子プロセスも起動")
    return parser.parse_args()


def _setup_logging(config: Config) -> None:
    from iris.kernel.logging import setup_logging

    setup_logging(config.logging)


def _check_environment(config: Config) -> bool:
    from rich.console import Console

    from iris.llm.llm_bridge import get_provider_class

    console = Console()
    provider_cls = get_provider_class(config.model.provider)
    ok = provider_cls.ensure_environment(config.model)
    if not ok:
        console.print("[bold red]環境チェックに失敗しました。終了します。[/bold red]")
    return ok


def run() -> None:
    args = _parse_args()
    project_root = Path(__file__).parent
    config = Config.load(str(project_root / "config.yaml"))

    if args.verbose:
        config.logging.console_level = "DEBUG"
    _setup_logging(config)

    if not _check_environment(config):
        return

    supervisor = Supervisor(config, spawn_input=args.input, spawn_output=args.output)
    supervisor.start()
    supervisor.wait()


if __name__ == "__main__":
    run()
