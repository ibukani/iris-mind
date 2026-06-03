"""LLMBridge のキャッシュキー・環境検証関連テスト。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessageChunk, HumanMessage
import pytest

from iris.kernel.config import ModelConfig
from iris.llm.bridge import LLMBridge, _hash_key

pytestmark = pytest.mark.legacy


def test_hash_key_deterministic() -> None:
    assert _hash_key("secret") == _hash_key("secret")
    assert _hash_key("") == ""
    assert _hash_key("key1") != _hash_key("key2")


def test_hash_key_does_not_leak_raw_key() -> None:
    h = _hash_key("my-super-secret-api-key")
    assert "my-super-secret-api-key" not in h
    assert len(h) == 16


def test_separate_models_get_separate_chat_models() -> None:
    config = ModelConfig(
        models=[
            {"name": "qwen3.5:9b", "roles": ["low"], "provider": "ollama"},
            {"name": "qwen3.5:14b", "roles": ["medium"], "provider": "ollama"},
        ],
    )
    bridge = LLMBridge(config)

    assert "qwen3.5:9b" in bridge._chat_models
    assert "qwen3.5:14b" in bridge._chat_models
    assert bridge._chat_models["qwen3.5:9b"] is not bridge._chat_models["qwen3.5:14b"]


def test_same_provider_entries_share_provider_instance() -> None:
    config = ModelConfig(
        models=[
            {"name": "model-a", "roles": ["default"], "provider": "ollama"},
            {"name": "model-b", "roles": ["smart"], "provider": "ollama"},
        ],
    )
    bridge = LLMBridge(config)

    assert bridge._model_providers["model-a"] is bridge._model_providers["model-b"]


def test_resolve_chat_model_by_name() -> None:
    config = ModelConfig(
        models=[
            {"name": "model-a", "roles": ["default"], "provider": "ollama"},
            {"name": "model-b", "roles": ["smart"], "provider": "ollama"},
        ],
    )
    bridge = LLMBridge(config)
    assert bridge._resolve_chat_model("model-a") is bridge._chat_models["model-a"]
    assert bridge._resolve_chat_model("model-b") is bridge._chat_models["model-b"]


def test_resolve_chat_model_unknown_falls_back() -> None:
    config = ModelConfig(
        models=[{"name": "only-model", "roles": ["default"], "provider": "ollama"}],
    )
    bridge = LLMBridge(config)
    result = bridge._resolve_chat_model("nonexistent")
    assert result is bridge._chat_models["only-model"]


def test_get_default_model_returns_first_chat_model() -> None:
    config = ModelConfig(
        models=[
            {"name": "first", "roles": ["default"], "provider": "ollama"},
            {"name": "second", "roles": ["smart"], "provider": "ollama"},
        ],
    )
    bridge = LLMBridge(config)
    assert bridge._get_default_model() == "first"


def test_unload_model_calls_provider() -> None:
    config = ModelConfig(
        models=[{"name": "m1", "roles": ["default"], "provider": "ollama"}],
    )
    bridge = LLMBridge(config)
    mock_provider = MagicMock()
    bridge._model_providers["m1"] = mock_provider

    bridge.unload_model("m1")
    mock_provider.unload.assert_called_once_with("m1", bridge._chat_models["m1"])


def test_unload_model_unknown_noop() -> None:
    config = ModelConfig(
        models=[{"name": "m1", "roles": ["default"], "provider": "ollama"}],
    )
    bridge = LLMBridge(config)
    bridge.unload_model("nonexistent")


def test_unload_model_none_noop() -> None:
    config = ModelConfig(
        models=[{"name": "m1", "roles": ["default"], "provider": "ollama"}],
    )
    bridge = LLMBridge(config)
    bridge.unload_model(None)


def test_stream_breaks_on_cancellation() -> None:
    bridge = LLMBridge(ModelConfig(models=[{"name": "test", "roles": ["default"], "provider": "ollama"}]))

    model_name = next(iter(bridge._chat_models))

    call_count = 0

    async def mock_astream(*args, **kwargs):
        nonlocal call_count
        for i in range(10):
            call_count += 1
            yield AIMessageChunk(content=f"chunk-{i}")

    mock_model = AsyncMock()
    mock_model.astream = mock_astream
    bridge._chat_models[model_name] = mock_model

    mock_provider = MagicMock()
    mock_provider.build_call_kwargs.return_value = {}
    bridge._model_providers[model_name] = mock_provider

    from iris.llm.interrupt_token import InterruptToken

    interrupt = InterruptToken()

    def on_token(tok: str) -> None:
        if tok == "chunk-2":
            interrupt.cancel()

    resp = asyncio.run(
        bridge.chat(
            messages=[HumanMessage(content="hi")],
            on_token=on_token,
            interrupt_token=interrupt,
        )
    )
    assert call_count == 3
    assert resp.content == "chunk-0chunk-1chunk-2"
