"""Ollama Environment Management — Ollama 環境管理ユーティリティ。

Ollama プロセスの起動、停止、および必要なモデルの pull を行う。
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
from typing import Any

from loguru import logger
from ollama import Client

from iris.kernel.config import ModelConfig, ModelEntry

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_IS_WINDOWS = sys.platform == "win32"


def ensure_environment(entries: list[ModelEntry], model_config: ModelConfig) -> bool:
    """Ollama 環境を確認・準備する（再起動 → モデル確認 → pull）。"""
    default_gpu = model_config.default_num_gpu if entries else 99
    os.environ.setdefault("OLLAMA_GPU_LAYERS", str(default_gpu))
    _restart_ollama()
    model_names = [e.name for e in entries]
    _stop_config_models(model_names)
    time.sleep(0.5)
    return all(_ensure_model_pulled(name) for name in model_names)


def _restart_ollama() -> None:
    """既存 Ollama プロセスを終了し、GPU 向け設定で再起動する。"""
    with contextlib.suppress(Exception):
        if _IS_WINDOWS:
            subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"], capture_output=True, timeout=5)
        else:
            subprocess.run(["pkill", "-f", "ollama"], capture_output=True, timeout=5)
    time.sleep(2)

    popen_kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if _IS_WINDOWS:
        popen_kwargs["creationflags"] = _CREATE_NO_WINDOW
    subprocess.Popen(["ollama", "serve"], **popen_kwargs)
    time.sleep(5)


def _stop_config_models(model_names: list[str]) -> None:
    """指定されたモデルを停止する。"""
    for name in model_names:
        with contextlib.suppress(Exception):
            subprocess.run(["ollama", "stop", name], capture_output=True, timeout=10)


def _get_available_models() -> set[str]:
    """Ollama に既に pull 済みのモデル名のセットを返す。"""
    try:
        client = Client()
        response = client.list()
        models: set[str] = set()
        for model in response.get("models", []):
            if isinstance(model, dict):
                name = model.get("model") or model.get("name") or ""
            else:
                name = getattr(model, "model", "") or getattr(model, "name", "")
            if name and ":" in name:
                models.add(name.split(":")[0])
            elif name:
                models.add(name)
        return models
    except Exception:
        return set()


def _ensure_model_pulled(model_name: str) -> bool:
    """モデルが存在しない場合はユーザーに確認して pull する。"""
    model_base = model_name.split(":")[0]
    available = _get_available_models()
    if model_base in available:
        return True

    try:
        console_input = input(
            f"モデル '{model_name}' が見つかりません。\n  ollama pull {model_name}\nを実行してダウンロードしますか？ [y/N] "
        )
    except EOFError:
        logger.warning("Non-interactive environment: skipping model pull for '%s'", model_name)
        return False
    if console_input.strip().lower() in ("y", "yes"):
        try:
            subprocess.run(
                ["ollama", "pull", model_name],
                check=True,
                timeout=600,
            )
            return True
        except subprocess.CalledProcessError:
            print(f"モデル '{model_name}' のダウンロードに失敗しました。", file=sys.stderr)
            return False
        except subprocess.TimeoutExpired:
            print(f"モデル '{model_name}' のダウンロードがタイムアウトしました。", file=sys.stderr)
            return False
    return False
