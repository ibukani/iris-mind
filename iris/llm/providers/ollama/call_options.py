"""call_options — Ollama ChatOllama 生成オプションと呼び出しパラメータ。"""

from __future__ import annotations

from typing import Any

from iris.kernel.config import ModelConfig, ModelEntry


def build_create_options(
    entry: ModelEntry,
    model_config: ModelConfig,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "num_ctx": entry.num_ctx if entry.num_ctx is not None else model_config.default_num_ctx,
        "num_gpu": entry.num_gpu if entry.num_gpu is not None else model_config.default_num_gpu,
    }
    if entry.presence_penalty is not None:
        options["presence_penalty"] = entry.presence_penalty
    if entry.frequency_penalty is not None:
        options["frequency_penalty"] = entry.frequency_penalty
    if entry.repeat_penalty is not None:
        options["repeat_penalty"] = entry.repeat_penalty
    return options


def build_call_options(
    temperature: float,
    max_tokens: int,
    entry: ModelEntry | None,
    kwargs: dict[str, Any],
    default_num_ctx: int = 8192,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "temperature": temperature,
        "num_predict": max_tokens,
    }
    if entry and getattr(entry, "repeat_penalty", None) is not None:
        options["repeat_penalty"] = entry.repeat_penalty
    for k in ("presence_penalty", "frequency_penalty", "repeat_penalty"):
        if k in kwargs:
            options[k] = kwargs.pop(k)
    num_ctx = kwargs.pop("num_ctx", None)
    if num_ctx is not None:
        options["num_ctx"] = num_ctx
    return options
