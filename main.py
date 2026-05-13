#!/usr/bin/env python3
"""Iris - 自律的に行動し進化できるAI"""

import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("OLLAMA_GPU_LAYERS", "99")


def _get_available_models() -> set[str]:
    """Ollamaに既にpull済みのモデル名のセットを返す。"""
    try:
        result = subprocess.run(
            ["ollama", "list", "--format", "json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            import json
            models = json.loads(result.stdout)
            return {m["model"].split(":")[0] for m in models if "model" in m}
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
        f"モデル '{model_name}' が見つかりません。\n"
        f"  ollama pull {model_name}\n"
        f"を実行してダウンロードしますか？ [y/N] "
    )
    if console_input.strip().lower() in ("y", "yes"):
        try:
            subprocess.run(
                ["ollama", "pull", model_name],
                check=True, timeout=600,
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
    try:
        subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"],
                       capture_output=True, timeout=5)
    except Exception:
        pass
    time.sleep(2)

    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    time.sleep(5)


def _stop_config_models(config: dict):
    """config.yamlに記載されたモデルを停止する。"""
    model_section = config.get("model", {})
    for key in ("smart_model", "fast_model", "draft_model"):
        m = model_section.get(key)
        if m:
            try:
                subprocess.run(["ollama", "stop", m],
                               capture_output=True, timeout=10)
            except Exception:
                pass


def _ensure_config_models(config_path: Path) -> bool:
    """config.yamlのモデルがpull済みか確認する（yamlはここで1回だけパース）。"""
    import yaml
    raw = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    config = yaml.safe_load(raw) if raw else {}

    _stop_config_models(config)
    time.sleep(0.5)

    model_section = config.get("model", {})
    for key in ("smart_model", "fast_model", "draft_model"):
        m = model_section.get(key)
        if m and not _ensure_model_pulled(m):
            return False
    return True


def run():
    """アプリケーションのエントリーポイント。"""
    project_root = Path(__file__).parent
    config_path = project_root / "config.yaml"

    _restart_ollama()

    if not _ensure_config_models(config_path):
        print("必要なモデルが利用できません。プログラムを終了します。", file=sys.stderr)
        sys.exit(1)

    from core.config import Config
    from core.llm_bridge import LLMBridge
    from core.cli import CliSession

    config = Config.load(str(config_path))

    llm = LLMBridge(
        model_name=config.model.smart_model,
        base_url=config.model.base_url,
        draft_model=config.model.draft_model,
        num_draft=config.model.num_draft,
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