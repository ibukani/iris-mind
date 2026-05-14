from __future__ import annotations

from iris.kernel.reflexion import Reflexion
from tests.conftest import FakeLLMProvider

TWO = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]


def _make_reflexion(response_json: str, compact_model: str | None = None) -> Reflexion:
    llm = FakeLLMProvider(responses=[{"message": {"content": response_json, "role": "assistant"}}])
    return Reflexion(llm=llm, compact_model=compact_model)


def test_reflect_parses_valid_json() -> None:
    reflexion = _make_reflexion(
        '{"summary": "test", "lesson": "learned", "preference": "likes X", "improvement": "be better", "speech_style": "friendly"}'  # noqa: E501
    )
    result = reflexion.reflect(TWO)
    assert result["summary"] == "test"
    assert result["lesson"] == "learned"
    assert result["preference"] == "likes X"
    assert result["improvement"] == "be better"
    assert result["speech_style"] == "friendly"


def test_reflect_empty_response_falls_back() -> None:
    reflexion = _make_reflexion("")
    result = reflexion.reflect(TWO)
    # Fallback uses raw content[:100] as summary
    assert result["summary"] == ""
    assert result["lesson"] == ""


def test_reflect_invalid_json_falls_back() -> None:
    reflexion = _make_reflexion("not json")
    result = reflexion.reflect(TWO)
    # Fallback puts raw content in summary, other keys are empty
    assert result["summary"] == "not json"
    assert result["lesson"] == ""


def test_reflect_short_history_returns_empty() -> None:
    reflexion = _make_reflexion("{}")
    result = reflexion.reflect([{"role": "user", "content": "only one"}])
    assert result == {
        "summary": "",
        "lesson": "",
        "preference": "",
        "improvement": "",
        "missing_capability": "",
        "speech_style": "",
        "expressed_traits": "",
        "user_reaction": "",
    }


def test_quick_reflect_returns_llm_response() -> None:
    reflexion = _make_reflexion(
        '{"speech_style": "casual", "expressed_traits": "curious", "user_reaction": "positive"}'
    )
    result = reflexion.quick_reflect(TWO)
    assert result.get("speech_style") == "casual"
    assert result.get("expressed_traits") == "curious"
    assert result.get("user_reaction") == "positive"


def test_quick_reflect_empty_json() -> None:
    reflexion = _make_reflexion("{}")
    result = reflexion.quick_reflect(TWO)
    assert all(v == "" for v in result.values())


def test_quick_reflect_short_history() -> None:
    reflexion = _make_reflexion("{}")
    result = reflexion.quick_reflect([{"role": "user", "content": "only one"}])
    assert result == {"speech_style": "", "expressed_traits": "", "user_reaction": ""}


def test_should_add_capability_true() -> None:
    reflexion = _make_reflexion("{}")
    assert reflexion.should_add_capability({"missing_capability": "web_search"}) is True


def test_should_add_capability_false() -> None:
    reflexion = _make_reflexion("{}")
    assert reflexion.should_add_capability({}) is False


def test_reflect_passes_messages_to_llm() -> None:
    llm = FakeLLMProvider(responses=[{"message": {"content": "{}", "role": "assistant"}}])
    reflexion = Reflexion(llm=llm)
    reflexion.reflect(TWO)
    assert len(llm._messages_log) == 1
    sent = llm._messages_log[0]
    assert any("hello" in str(m) for m in sent)


def test_reflect_passes_compact_model() -> None:
    llm = FakeLLMProvider(responses=[{"message": {"content": "{}", "role": "assistant"}}])
    reflexion = Reflexion(llm=llm, compact_model="compact-model")
    reflexion.reflect(TWO)
    assert llm._model_log[-1] == "compact-model"


def test_quick_reflect_passes_compact_model() -> None:
    llm = FakeLLMProvider(responses=[{"message": {"content": "{}", "role": "assistant"}}])
    reflexion = Reflexion(llm=llm, compact_model="compact-model")
    reflexion.quick_reflect(TWO)
    assert llm._model_log[-1] == "compact-model"
