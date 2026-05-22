from __future__ import annotations

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
            }
        ]
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
    # "応答します。あ" * 10 = 応答します。ああああああああああ
    # match_single = re.search(r"((.)\2{9,})", text)
    # マッチするのは "あ" * 10
    # トリミング後は "あ" * 3
    assert bridge._trim_repetition(text) == expected


def test_chat_non_streaming_repetition() -> None:
    bridge = _make_bridge()
    from unittest.mock import AsyncMock

    mock_provider = AsyncMock()
    # 返り値に繰り返しを含める
    mock_provider.chat.return_value = {
        "message": {"role": "assistant", "content": "同じことを言います。全部、全部、全部、全部、"}
    }
    bridge._providers = {next(iter(bridge._providers)): mock_provider}

    import asyncio

    resp = asyncio.run(bridge.chat(messages=[{"role": "user", "content": "hello"}]))
    content = resp["message"]["content"]
    assert content == "同じことを言います。全部、全部、… [繰り返し検知により中断]"


def test_chat_streaming_repetition() -> None:
    bridge = _make_bridge()
    from unittest.mock import AsyncMock

    mock_provider = AsyncMock()

    # ストリーミングのモック動作
    # chatを呼んだときに on_token を順次呼び出し、最終的な返り値を返す
    async def mock_chat(*args, **kwargs) -> dict:
        on_token = kwargs.get("on_token")
        interrupt_token = kwargs.get("interrupt_token")

        tokens = ["これは", "ストリーム", "です。", "全部、", "全部、", "全部、", "全部、", "全部、"]
        content_parts = []
        for t in tokens:
            if interrupt_token and getattr(interrupt_token, "is_cancelled", False):
                break
            content_parts.append(t)
            if on_token:
                on_token(t)

        return {"message": {"role": "assistant", "content": "".join(content_parts)}}

    mock_provider.chat.side_effect = mock_chat
    bridge._providers = {next(iter(bridge._providers)): mock_provider}

    captured_tokens = []
    interrupt_token = InterruptToken()

    import asyncio

    resp = asyncio.run(
        bridge.chat(
            messages=[{"role": "user", "content": "hello"}],
            on_token=captured_tokens.append,
            interrupt_token=interrupt_token,
        )
    )

    # 4回目の「全部、」の時点でキャンセルされ、それ以降のトークンは呼ばれない
    assert captured_tokens == ["これは", "ストリーム", "です。", "全部、", "全部、", "全部、"]
    # 最終的なレスポンスもトリミングされている
    assert resp["message"]["content"] == "これはストリームです。全部、全部、… [繰り返し検知により中断]"
