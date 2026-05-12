#!/usr/bin/env python3
"""Iris - 自律的に行動し進化できるAI"""

import os
import subprocess
import sys
import time

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


def _cleanup_ollama_models():
    """GPU向け環境変数が反映された状態でOllamaサーバーを再起動し、
    config.yamlに記載のモデルがpull済みか確認する。"""
    # 既存Ollamaプロセスを強制終了
    try:
        subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"],
                       capture_output=True, timeout=5)
    except Exception:
        pass
    time.sleep(2)

    # 環境変数 OLLAMA_GPU_LAYERS=99 を反映して起動
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    time.sleep(5)

    # config.yamlに記載のモデルを解放
    try:
        import yaml
        from pathlib import Path
        p = Path(__file__).parent / "config.yaml"
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
        model_section = raw.get("model", {})
        for key in ("smart_model", "fast_model", "draft_model"):
            m = model_section.get(key)
            if m:
                subprocess.run(["ollama", "stop", m],
                               capture_output=True, timeout=10)
    except Exception:
        pass
    time.sleep(0.5)


_cleanup_ollama_models()

# config.yamlに記載のモデルがpull済みか確認・ダウンロード
_config_available = True
try:
    import yaml
    from pathlib import Path
    p = Path(__file__).parent / "config.yaml"
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    model_section = raw.get("model", {})
    for key in ("smart_model", "fast_model", "draft_model"):
        m = model_section.get(key)
        if m and not _ensure_model_pulled(m):
            _config_available = False
except Exception:
    pass

if not _config_available:
    print("必要なモデルが利用できません。プログラムを終了します。", file=sys.stderr)
    sys.exit(1)


_cleanup_ollama_models()

from core.cli import run_cli

if __name__ == "__main__":
    run_cli()
