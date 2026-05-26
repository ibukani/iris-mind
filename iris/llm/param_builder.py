from __future__ import annotations

from typing import Any

_PROVIDER_DEFAULTS: dict[str, str] = {
    "ollama": "http://localhost:11434",
    "openrouter": "https://openrouter.ai/api/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
}


def build_ollama_options(
    temperature: float,
    max_tokens: int,
    entry: Any,
    kwargs: dict[str, Any],
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
    return options


def build_openai_kwargs(
    temperature: float,
    max_tokens: int,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    call_kwargs: dict[str, Any] = {
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    for k in ("presence_penalty", "frequency_penalty"):
        if k in kwargs:
            call_kwargs[k] = kwargs.pop(k)
    return call_kwargs
