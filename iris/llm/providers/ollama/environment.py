"""environment — Ollama 実行環境のセットアップ。"""

from __future__ import annotations

import os

from iris.kernel.config import ModelConfig, ModelEntry


def set_ollama_env_vars(entries: list[ModelEntry], model_config: ModelConfig) -> None:
    """OLLAMA_GPU_LAYERS / OLLAMA_FLASH_ATTENTION を設定する。"""
    default_gpu = model_config.default_num_gpu if entries else 99
    os.environ.setdefault("OLLAMA_GPU_LAYERS", str(default_gpu))
    os.environ["OLLAMA_FLASH_ATTENTION"] = "1"
