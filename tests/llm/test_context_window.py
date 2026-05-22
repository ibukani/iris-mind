from __future__ import annotations

from iris.llm.context import LLMContextWindowManager, estimate_messages_tokens, estimate_tokens
from tests.conftest import FakeLLMProvider


def test_estimate_tokens() -> None:
    # 日本語フォールバックのテスト
    assert estimate_tokens("こんにちは") == 6  # 5 * 1.3 = 6.5 -> 6 (int)
    assert estimate_tokens("") == 0


def test_estimate_messages_tokens() -> None:
    msgs = [
        {"role": "user", "content": "あ"},
        {"role": "assistant", "content": "い"},
    ]
    assert estimate_messages_tokens(msgs) == 2


def test_check_and_summarize_no_trigger() -> None:
    llm = FakeLLMProvider()
    mgr = LLMContextWindowManager(llm=llm, compact_model="test-model")

    # 閾値未満なので要約されない
    messages = [{"role": "user", "content": "test"}] * 10
    summary = mgr.check_and_summarize(messages, context_window=1000, threshold=0.85, preserve_last=4)
    assert summary == ""


def test_check_and_summarize_trigger() -> None:
    # 要約がトリガーされるケース
    fake_response = {"message": {"content": "要約された内容", "role": "assistant"}}
    llm = FakeLLMProvider(responses=[fake_response])
    mgr = LLMContextWindowManager(llm=llm, compact_model="test-model")

    # メッセージ総トークン数が閾値を超えるように構成
    messages = [{"role": "user", "content": "長い日本語メッセージです。" * 20}] * 10
    # estimate_tokens: "長い日本語メッセージです。" * 20 -> 13文字 * 20 = 260文字 -> 260 * 1.3 = 338 tokens
    # 10メッセージで約3380 tokens。context_window=1000 だと余裕で超える
    summary = mgr.check_and_summarize(messages, context_window=1000, threshold=0.8, preserve_last=2)
    assert summary == "要約された内容"
    assert mgr.summary == "要約された内容"

    # 送信されたメッセージの確認
    assert len(llm._messages_log) == 1
    compact_call = llm._messages_log[0]

    # 最後のシステムプロンプト指示とユーザープロンプト
    assert compact_call[0]["role"] == "system"
    assert compact_call[1]["role"] == "user"
    assert "要約された内容" not in compact_call[1]["content"]  # 初回なので過去の要約は含まれない


def test_summarize_keeps_previous_summary() -> None:
    # 既存の要約が存在する場合、引き継がれるテスト
    fake_response = {"message": {"content": "統合要約", "role": "assistant"}}
    llm = FakeLLMProvider(responses=[fake_response])
    mgr = LLMContextWindowManager(llm=llm, compact_model="test-model")
    mgr._summary = "以前の要約"

    messages = [
        {"role": "user", "content": "追加メッセージ1"},
        {"role": "assistant", "content": "追加メッセージ2"},
    ]

    summary = mgr.summarize(messages)
    assert summary == "統合要約"

    # 送信メッセージの確認
    compact_call = llm._messages_log[0]
    user_content = compact_call[1]["content"]
    assert "以前の要約" in user_content
    assert "追加メッセージ1" in user_content
    assert "追加メッセージ2" in user_content
