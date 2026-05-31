"""model_admin — Ollama モデル管理（再起動・停止・プル・確認）。"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import time
from typing import Any

from loguru import logger

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_IS_WINDOWS = sys.platform == "win32"


def restart_ollama() -> None:
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


def stop_models(model_names: list[str]) -> None:
    for name in model_names:
        with contextlib.suppress(Exception):
            subprocess.run(["ollama", "stop", name], capture_output=True, timeout=10)


def extract_model_name(model: Any) -> str:
    name = ""
    if isinstance(model, dict):
        name = model.get("model") or model.get("name") or ""
    else:
        name = getattr(model, "model", "") or getattr(model, "name", "")
    return name.split(":")[0] if ":" in name else name


def get_available_models() -> set[str]:
    from ollama import Client

    try:
        response = Client().list()
        names = [extract_model_name(m) for m in response.get("models", [])]
        return {n for n in names if n}
    except Exception:
        return set()


def ensure_model_pulled(model_name: str) -> bool:
    model_base = model_name.split(":")[0]
    if model_base in get_available_models():
        return True
    if not confirm_pull(model_name):
        return False
    try:
        subprocess.run(["ollama", "pull", model_name], check=True, timeout=600)
        return True
    except subprocess.CalledProcessError:
        print(f"モデル '{model_name}' のダウンロードに失敗しました。", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print(f"モデル '{model_name}' のダウンロードがタイムアウトしました。", file=sys.stderr)
        return False


def confirm_pull(model_name: str) -> bool:
    try:
        resp = input(
            f"モデル '{model_name}' が見つかりません。\n  ollama pull {model_name}\nを実行してダウンロードしますか？ [y/N] ",
        )
    except EOFError:
        logger.warning("Non-interactive environment: skipping model pull for '{}'", model_name)
        return False
    return resp.strip().lower() in ("y", "yes")
