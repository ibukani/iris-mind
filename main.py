#!/usr/bin/env python3
"""Iris Kernel — 3-Process アーキテクチャの中核プロセス。

起動方法:
    python main.py

Input / Output アダプターは別プロセスとして起動し、Named Pipe 経由で接続する。
"""

from pathlib import Path

from iris.kernel.config import Config
from iris.kernel.core import KernelProcess


def run() -> None:
    project_root = Path(__file__).parent
    config = Config.load(str(project_root / "config.yaml"))

    from iris.kernel.logging import setup_logging

    setup_logging(config.logging)

    if not _check_environment(config):
        return

    KernelProcess(config).launch()


def _check_environment(config: Config) -> bool:
    from rich.console import Console

    from iris.llm.llm_bridge import get_provider_class

    console = Console()
    provider_cls = get_provider_class(config.model.provider)
    ok = provider_cls.ensure_environment(config.model)

    if not ok:
        console.print("[bold red]環境チェックに失敗しました。終了します。[/bold red]")
    return ok


if __name__ == "__main__":
    run()
