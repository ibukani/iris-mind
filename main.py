#!/usr/bin/env python3
"""Iris - 自律的に行動し進化できるAI"""

import contextlib
import os
import subprocess
import sys
import time
from pathlib import Path

from core.config import Config

os.environ.setdefault("OLLAMA_GPU_LAYERS", "99")


def _get_available_models() -> set[str]:
    """Ollamaに既にpull済みのモデル名のセットを返す。"""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().splitlines()
            models: set[str] = set()
            for line in lines[2:]:
                if line.strip():
                    name = line.strip().split()[0]
                    if ":" in name:
                        models.add(name.split(":")[0])
            return models
    except Exception:
        pass
    return set()


def _ensure_model_pulled(model_name: str) -> bool:
    """モデルが存在しない場合はユーザーに確認してpullする。pull済みまたはスキップならTrue。"""
    model_base = model_name.split(":")[0]
    available = _get_available_models()
    if model_base in available:
        return True

    console_input = input(
        f"モデル '{model_name}' が見つかりません。\n  ollama pull {model_name}\nを実行してダウンロードしますか？ [y/N] "
    )
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


def _restart_ollama():
    """既存Ollamaプロセスを終了し、GPU向け設定で再起動する。"""
    with contextlib.suppress(Exception):
        subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"], capture_output=True, timeout=5)
    time.sleep(2)

    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    time.sleep(5)


def _stop_config_models(config: Config):
    """Configに記載されたモデルを停止する。"""
    for name in config.model.model_names:
        with contextlib.suppress(Exception):
            subprocess.run(["ollama", "stop", name], capture_output=True, timeout=10)


def _ensure_config_models(config: Config) -> bool:
    """Configのモデルがpull済みか確認する。"""
    _stop_config_models(config)
    time.sleep(0.5)

    return all(_ensure_model_pulled(name) for name in config.model.model_names)


def run():
    """アプリケーションのエントリーポイント。"""
    project_root = Path(__file__).parent
    config_path = project_root / "config.yaml"

    config = Config.load(str(config_path))

    _restart_ollama()

    if not _ensure_config_models(config):
        print("必要なモデルが利用できません。プログラムを終了します。", file=sys.stderr)
        sys.exit(1)

    from core.cli import CliSession
    from core.llm_bridge import LLMBridge

    llm = LLMBridge(
        model_name=config.model.base_model,
        base_url=config.model.base_url,
        num_gpu=config.model.num_gpu,
        num_ctx=config.model.num_ctx,
    )

    if not llm.is_available():
        print("Ollamaサーバーに接続できませんでした。", file=sys.stderr)
        sys.exit(1)

    session = CliSession(config, llm)
    session.run()


if __name__ == "__main__":
    run()
