#!/usr/bin/env python3
"""Iris - 自律的に行動し進化できるAI"""

import os
import time

os.environ.setdefault("OLLAMA_GPU_LAYERS", "99")


def _cleanup_ollama_models():
    """GPU向け環境変数が反映された状態でOllamaサーバーを再起動する。"""
    import subprocess

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

from core.cli import run_cli

if __name__ == "__main__":
    run_cli()
