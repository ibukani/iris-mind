#!/usr/bin/env python3
"""Iris - 自律的に行動し進化できるAI (v0.3)"""

import argparse
import os
from pathlib import Path

from adapters.cli.server import CLIAdapter
from iris.kernel.config import Config
from iris.kernel.controller import IrisController
from iris.kernel.factory import KernelFactory

os.environ.setdefault("OLLAMA_GPU_LAYERS", "99")


def run() -> None:
    parser = argparse.ArgumentParser(description="Iris AI Assistant")
    parser.add_argument(
        "--separate",
        action="store_true",
        help="Input / Kernel / Output を別プロセスとして起動する",
    )
    parser.add_argument(
        "--no-input",
        action="store_true",
        help="Input Process を起動しない (--separate 時、デバッグ用)",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Output Process を起動しない (--separate 時、デバッグ用)",
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent
    config = Config.load(str(project_root / "config.yaml"))

    from iris.kernel.logging import setup_logging

    setup_logging(config.logging)

    if not _check_environment(config):
        return

    if args.separate:
        IrisController(
            config,
            enable_input=not args.no_input,
            enable_output=not args.no_output,
        ).launch()
    else:
        ctx = KernelFactory.build(config)
        CLIAdapter(ctx).run()


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
