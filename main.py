#!/usr/bin/env python3
"""Iris Supervisor — Kernel プロセスの起動を担当するエントリポイント。

起動方法:
    python main.py                          # Supervisor 起動
    python main.py --verbose                # Kernel 診断ログを stderr に出力
"""

from __future__ import annotations

import argparse
from pathlib import Path

from iris.kernel.config import Config
from iris.kernel.core.supervisor import Supervisor


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Iris Supervisor")
    parser.add_argument("--verbose", action="store_true", help="Kernel 診断ログを stderr に出力")
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

    Supervisor(config).run()


if __name__ == "__main__":
    run()
