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
        "--output-separate",
        action="store_true",
        help="Output Process を別プロセスとして起動する",
    )
    parser.add_argument(
        "--separate",
        action="store_true",
        help="Input / Kernel / Output を別プロセスとして起動する (3-Process)",
    )
    parser.add_argument(
        "--no-input",
        action="store_true",
        help="Input Process を起動しない (デバッグ用)",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Output Process を起動しない (デバッグ用)",
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent
    config = Config.load(str(project_root / "config.yaml"))

    from iris.kernel.logging import setup_logging

    setup_logging(config.logging)

    if not _check_environment(config):
        return

    if args.separate:
        IrisController(config).launch()
    elif args.output_separate:
        ctx = KernelFactory.build(config)
        _run_output_separated(ctx)
    else:
        ctx = KernelFactory.build(config)
        CLIAdapter(ctx).run()


def _run_output_separated(ctx):  # noqa: ANN001, ANN201
    import subprocess
    import sys
    import time
    from datetime import datetime

    from rich.console import Console

    from iris.kernel.event import UserInputEvent
    from iris.kernel.ipc import PIPE_NAME_KERNEL_OUTPUT
    from iris.kernel.ipc_output import OutputBridge

    console = Console()
    output_bridge = OutputBridge(ctx.event_bus, PIPE_NAME_KERNEL_OUTPUT)
    output_bridge.start()

    output_process = subprocess.Popen(
        [sys.executable, "-m", "adapters.cli.output_main", PIPE_NAME_KERNEL_OUTPUT],
    )
    time.sleep(0.5)

    console.print("[bold cyan]Iris CLI (output-separate mode)[/bold cyan]")
    console.print("Type your message. [dim]Ctrl+C or 'exit' to quit.[/dim]")
    console.print()

    try:
        while True:
            try:
                text = input(">>> ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break

            if not text:
                continue
            if text.lower() in ("exit", "quit"):
                break

            if text.startswith("/"):
                ctx.proactive.notify_user_activity()
                response = ctx.cmd_handler.handle(text)
                if response:
                    console.print(f"[bold cyan][System][/bold cyan] {response}")
                continue

            ctx.event_bus.publish(
                UserInputEvent(
                    timestamp=datetime.now(),
                    source="user_input",
                    content=text,
                )
            )
    finally:
        output_process.terminate()
        output_process.wait(timeout=3)
        output_bridge.stop()
        import contextlib

        with contextlib.suppress(Exception):
            ctx.conversation.session_reflect()
        ctx.kernel.shutdown()
        console.print("[dim]Shutdown complete.[/dim]")


def _check_environment(config: Config) -> bool:
    """LLMプロバイダの環境を確認する。"""
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
