from __future__ import annotations

from iris.kernel.services import ContextManager
from iris.kernel.services.context import estimate_messages_tokens, estimate_tokens
from tests.conftest import FakeLLMProvider


def test_estimate_tokens_empty() -> None:
    assert estimate_tokens("") == 0


def test_estimate_tokens_short() -> None:
    count = estimate_tokens("hello")
    assert count > 0
    assert count <= 10


def test_estimate_tokens_long() -> None:
    text = "word " * 1000
    count = estimate_tokens(text)
    assert count > 500
    assert count < 3000


def test_estimate_messages_tokens() -> None:
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    count = estimate_messages_tokens(messages)
    assert count > 0


def test_check_and_summarize_below_threshold() -> None:
    llm = FakeLLMProvider()
    ctx = ContextManager(llm=llm, compact_model="test-model")
    messages = [{"role": "user", "content": "hi"}]
    result = ctx.check_and_summarize(messages, context_window=1000, threshold=0.9)
    assert result == ""
    assert ctx.has_summary is False


def test_force_summarize() -> None:
    llm = FakeLLMProvider()
    ctx = ContextManager(llm=llm, compact_model="test-model")
    messages = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    result = ctx.force_summarize(messages, preserve_last=1)
    assert isinstance(result, str)


def test_build_compact_messages() -> None:
    llm = FakeLLMProvider()
    ctx = ContextManager(llm=llm, compact_model="test-model")
    ctx._summary = "Test summarization result."

    messages = [
        {"role": "user", "content": "first msg"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "second msg"},
        {"role": "assistant", "content": "second reply"},
    ]
    compact = ctx.build_compact_messages(messages, preserve_last=2)
    assert len(compact) >= 1
    system_count = sum(1 for m in compact if m["role"] == "system")
    assert system_count >= 1
    preserved = [m for m in compact if m["role"] != "system"]
    assert len(preserved) <= 2


def test_clear() -> None:
    llm = FakeLLMProvider()
    ctx = ContextManager(llm=llm, compact_model="test-model")
    ctx._summary = "dummy"
    ctx.clear()
    assert ctx.has_summary is False
