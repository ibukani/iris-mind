#!/usr/bin/env python3
"""Iris - 自律的に行動し進化できるAI (v0.2)"""

import os
import sys
from pathlib import Path

from iris.kernel.config import Config

os.environ.setdefault("OLLAMA_GPU_LAYERS", "99")


def run():
    """アプリケーションのエントリーポイント。"""
    project_root = Path(__file__).parent
    config_path = project_root / "config.yaml"
    config = Config.load(str(config_path))

    if config.model.provider == "ollama":
        from iris.llm.ollama_provider import OllamaProvider

        ok = OllamaProvider.ensure_environment(config.model)
    else:
        from iris.llm.openrouter_provider import OpenRouterProvider

        ok = OpenRouterProvider.ensure_environment(config.model)

    if not ok:
        sys.exit(1)

    from adapters.cli.server import main as cli_main

    cli_main()


if __name__ == "__main__":
    run()
