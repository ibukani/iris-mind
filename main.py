#!/usr/bin/env python3
"""Iris Supervisor — プロセス起動・監視・シャットダウンを担当するエントリポイント。

起動方法:
    python main.py                          # Kernel のみ（デフォルト）
    python main.py --input --output         # Kernel + Input + Output（開発用）
    python main.py --input                  # Kernel + Input
    python main.py --output                 # Kernel + Output
    python main.py --verbose                # Kernel 診断ログを stderr に出力

シャットダウン手順:

  Ctrl+C (SIGINT) / SIGTERM (Unix のみ)
    │
    └→ Supervisor (main.py)
          │
          ├─ 1. stop_bridge("input") → Input PipeServer をクローズ
          │      Input 子プロセス: PipeClient の送信失敗 → break → 終了
          │      _terminate(): 念のため terminate() + wait(5s)
          │
          ├─ 2. Kernel.shutdown():
          │      ├─ OutputBridge.stop()   → PipeServer クローズ
          │      ├─ InputBridge.stop()    → PipeServer クローズ
          │      ├─ session_reflect()
          │      └─ agent_kernel.shutdown()
          │
          ├─ 3. stop_bridge("output") → Output PipeServer をクローズ
          │      0.5s 待機（Output が最後の応答を表示し切る猶予）
          │      Output 子プロセス: PipeClient.recv() 失敗 → break → 終了
          │      _terminate(): 念のため terminate() + wait(5s)
          │
          └─ 4. 完了ログ

  子プロセスの主要終了経路は Pipe 切断検知。
  terminate() / kill() はタイムアウト時の保険であり、正常系では不要。
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
    """シャットダウン順序: Input → Kernel → Output"""
    logger.info("Supervisor: shutting down all processes")

    # 1. Input を止める（ユーザー入力を遮断）
    if input_proc is not None:
        kernel.stop_bridge("input")
        _terminate(input_proc, "Input Process")

    # 2. Kernel を止める
    kernel.shutdown()

    # 3. Output を止める（最後: Kernel の残した応答を出力し切る）
    if output_proc is not None:
        kernel.stop_bridge("output")
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

    # Kernel プロセス起動（同一プロセス内）
    from iris.kernel.core import KernelProcess

    kernel: KernelProcessProtocol = KernelProcess(config)
    kernel.start()

    # Input / Output 子プロセス起動
    if args.input:
        from iris.kernel.ipc import PIPE_NAME_KERNEL_INPUT

        input_proc = _spawn(
            ["-m", "debug_tools.cli.input_main", PIPE_NAME_KERNEL_INPUT],
            "Input Process",
        )
    if args.output:
        from iris.kernel.ipc import PIPE_NAME_KERNEL_OUTPUT

        output_proc = _spawn(
            ["-m", "debug_tools.cli.output_main", PIPE_NAME_KERNEL_OUTPUT],
            "Output Process",
        )

    # シグナルハンドラ設定
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
    # Windows: SIGTERM は TerminateProcess 相当のためハンドラ不可。Ctrl+C (SIGINT) のみ

    # メインスレッド生存維持
    logger.info("Supervisor: running")
    try:
        while not shutdown_requested:
            time.sleep(1)
    except KeyboardInterrupt:
        if not shutdown_requested:
            _shutdown(kernel, input_proc, output_proc)


if __name__ == "__main__":
    run()
