#!/usr/bin/env python3
"""Iris Kernel — 3-Process アーキテクチャの中核プロセス。

起動方法:
    python main.py

Input / Output アダプターは別プロセスとして起動し、Named Pipe 経由で接続する。
"""

import os
from pathlib import Path

from iris.kernel.config import Config
from iris.kernel.kernel_process import KernelProcess

os.environ.setdefault("OLLAMA_GPU_LAYERS", "99")


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

    console = Console()
    cfg = config.model

    if cfg.provider == "ollama":
        from iris.llm.ollama_provider import OllamaProvider

        ok = OllamaProvider.ensure_environment(cfg)
    else:
        from iris.llm.openrouter_provider import OpenRouterProvider

        ok = OpenRouterProvider.ensure_environment(cfg)

    if not ok:
        console.print("[bold red]環境チェックに失敗しました。終了します。[/bold red]")
    return ok


if __name__ == "__main__":
    run()
