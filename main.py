#!/usr/bin/env python3
"""Iris - 自律的に行動し進化できるAI (v0.2)"""

import os
from pathlib import Path

from adapters.cli.server import CLIAdapter
from iris.kernel.config import Config

os.environ.setdefault("OLLAMA_GPU_LAYERS", "99")


def run():
    """アプリケーションのエントリーポイント。"""
    project_root = Path(__file__).parent
    config = Config.load(str(project_root / "config.yaml"))
    CLIAdapter(config).run()


if __name__ == "__main__":
    run()
