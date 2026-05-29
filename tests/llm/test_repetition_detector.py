from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from iris.kernel.config import ModelConfig
from iris.llm.bridge import LLMBridge
from iris.llm.interrupt_token import InterruptToken


def _make_bridge() -> LLMBridge:
    config = ModelConfig(
        models=[
            {
                "name": "test-model",
                "roles": ["default"],
                "provider": "ollama",
                "presence_penalty": 0.5,
                "frequency_penalty": 0.5,
                "repeat_penalty": 1.2,
            },
        ],
    )
    return LLMBridge(config)


def test_detect_repetition_normal() -> None:
    bridge = _make_bridge()
    assert bridge._detect_repetition("これは正常な文章です。繰り返しはありません。") is False
    assert bridge._detect_repetition("") is False


def test_detect_repetition_multi_chars() -> None:
    bridge = _make_bridge()
    # 2-20文字の繰り返しが4回以上連続
    assert bridge._detect_repetition("全部、全部、全部、全部、") is True
    assert bridge._detect_repetition("これは全部、全部、全部、全部、") is True
    # 3回以下は検知しない
    assert bridge._detect_repetition("全部、全部、全部、") is False


def test_detect_repetition_single_char() -> None:
    bridge = _make_bridge()
    # 1文字の繰り返しが10回以上連続
    assert bridge._detect_repetition("あ" * 10) is True
    assert bridge._detect_repetition("あ" * 9) is False


def test_trim_repetition_multi() -> None:
    bridge = _make_bridge()
    text = "何か新しいことはありませんか？全部、全部、全部、全部、"
    expected = "何か新しいことはありませんか？全部、全部、… [繰り返し検知により中断]"
    assert bridge._trim_repetition(text) == expected


def test_trim_repetition_single() -> None:
    bridge = _make_bridge()
    text = "応答します。" + "あ" * 10
    expected = "応答します。あああ… [繰り返し検知により中断]"
    assert bridge._trim_repetition(text) == expected


def test_chat_non_streaming_repetition() -> None:
    bridge = _make_bridge()

    model_key = next(iter(bridge._chat_models))
    model_name = next(iter(bridge._model_map))

    mock_model = AsyncMock()
    mock_model.ainvoke.return_value = AIMessage(content="同じことを言います。全部、全部、全部、全部、")
    bridge._chat_models[model_key] = mock_model

    mock_provider = MagicMock()
    mock_provider.build_call_kwargs.return_value = {}
    bridge._model_providers[model_name] = mock_provider

    resp = asyncio.run(bridge.chat(messages=[HumanMessage(content="hello")]))
    content = resp.content
    assert content == "同じことを言います。全部、全部、… [繰り返し検知により中断]"


def test_chat_streaming_repetition() -> None:
    bridge = _make_bridge()

    model_key = next(iter(bridge._chat_models))
    model_name = next(iter(bridge._model_map))

    mock_model = AsyncMock()

    async def mock_astream(*args, **kwargs):
        tokens = ["これは", "ストリーム", "です。", "全部、", "全部、", "全部、", "全部、", "全部、"]
        for t in tokens:
            yield AIMessageChunk(content=t)

    mock_model.astream = mock_astream
    bridge._chat_models[model_key] = mock_model

    mock_provider = MagicMock()
    mock_provider.build_call_kwargs.return_value = {}
    bridge._model_providers[model_name] = mock_provider

    captured_tokens = []
    interrupt_token = InterruptToken()

    resp = asyncio.run(
        bridge.chat(
            messages=[HumanMessage(content="hello")],
            on_token=captured_tokens.append,
            interrupt_token=interrupt_token,
        ),
    )

    # 4回目の「全部、」の時点でキャンセルされ、それ以降のトークンは呼ばれない
    assert captured_tokens == ["これは", "ストリーム", "です。", "全部、", "全部、", "全部、"]
    # 最終的なレスポンスもトリミングされている
    assert resp.content == "これはストリームです。全部、全部、… [繰り返し検知により中断]"
