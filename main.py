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


def _spawn(python_args: list[str], name: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable] + python_args,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    logger.info("Supervisor: spawned %s (pid=%d)", name, proc.pid)
    return proc


def _terminate(proc: subprocess.Popen | None, name: str, timeout: float = _SHUTDOWN_TIMEOUT) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=timeout)
        logger.info("Supervisor: %s terminated gracefully", name)
    except subprocess.TimeoutExpired:
        logger.warning("Supervisor: %s did not exit in %.1fs, killing", name, timeout)
        proc.kill()
        proc.wait(timeout=2)


def _shutdown(
    kernel: KernelProcessProtocol,
    input_proc: subprocess.Popen | None,
    output_proc: subprocess.Popen | None,
) -> None:
    logger.info("Supervisor: shutting down all processes")

    if input_proc is not None:
        _terminate(input_proc, "Input Process")

    kernel.shutdown()

    if output_proc is not None:
        time.sleep(0.5)
        _terminate(output_proc, "Output Process")

    logger.info("Supervisor: all processes terminated")


def run() -> None:
    args = _parse_args()
    project_root = Path(__file__).parent
    config = Config.load(str(project_root / "config.yaml"))

    if args.verbose:
        config.logging.console_level = "DEBUG"
    _setup_logging(config)

    if not _check_environment(config):
        return

    input_proc: subprocess.Popen | None = None
    output_proc: subprocess.Popen | None = None

    from iris.kernel.core import KernelProcess

    kernel: KernelProcessProtocol = KernelProcess(config)
    kernel.start()

    if args.input:
        from iris.kernel.io.models import PIPE_NAME_INPUT

        input_proc = _spawn(["-m", "debug_tools.cli.input_main", PIPE_NAME_INPUT], "Input Process")
    if args.output:
        from iris.kernel.io.models import PIPE_NAME_OUTPUT

        output_proc = _spawn(["-m", "debug_tools.cli.output_main", PIPE_NAME_OUTPUT], "Output Process")

    shutdown_requested = False

    def _on_signal(sig: int, _frame: object) -> None:
        nonlocal shutdown_requested
        if shutdown_requested:
            return
        shutdown_requested = True
        logger.info("Supervisor: received signal %d, starting shutdown", sig)
        _shutdown(kernel, input_proc, output_proc)
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_signal)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, _on_signal)

    logger.info("Supervisor: running")
    try:
        while not shutdown_requested:
            time.sleep(1)
    except KeyboardInterrupt:
        if not shutdown_requested:
            _shutdown(kernel, input_proc, output_proc)


if __name__ == "__main__":
    run()
