#!/usr/bin/env python3
"""Iris - 自律的に行動し進化できるAI (v0.2)"""

import contextlib
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

from iris.kernel.config import Config

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
    """モデルが存在しない場合はユーザーに確認してpullする。"""
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


def _ensure_openrouter_models(config: Config) -> bool:
    """OpenRouter に接続し、設定されたモデルが利用可能か確認する。"""
    base_url = config.model.base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {config.model.api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.get(f"{base_url}/models", headers=headers, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        remote_ids = {m["id"] for m in data.get("data", [])}
    except Exception as e:
        print(f"OpenRouter への接続に失敗しました: {e}", file=sys.stderr)
        return False

    ok = True
    for m in config.model.models:
        if m.name not in remote_ids:
            print(
                f"  警告: モデル '{m.name}' が OpenRouter のモデル一覧に見つかりません。"
                f" モデル名を確認してください。",
                file=sys.stderr,
            )
            ok = False
    if not ok:
        print("一部のモデルが見つかりませんが、起動を続行します。", file=sys.stderr)
    return True


def run():
    """アプリケーションのエントリーポイント。"""
    project_root = Path(__file__).parent
    config_path = project_root / "config.yaml"

    config = Config.load(str(config_path))

    if config.model.provider == "ollama":
        _restart_ollama()
        if not _ensure_config_models(config):
            print("必要なモデルが利用できません。プログラムを終了します。", file=sys.stderr)
            sys.exit(1)
    else:
        if not config.model.api_key or config.model.api_key.startswith("${"):
            print(
                "APIキーが設定されていません。config.yaml の model.api_key を確認してください。",
                file=sys.stderr,
            )
            sys.exit(1)
        _ensure_openrouter_models(config)

    from adapters.cli.server import main as cli_main

    cli_main()


if __name__ == "__main__":
    run()
