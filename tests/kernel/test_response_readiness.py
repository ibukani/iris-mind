from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from iris.kernel.config import ResponseReadinessConfig
from iris.kernel.services.response_readiness import ReadinessResult, ResponseReadinessEvaluator


class FakeLLMBridge:
    def __init__(self, response: str = "Yes") -> None:
        self._response = response
        self.call_count = 0

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 10,
        **kwargs: Any,
    ) -> dict:
        self.call_count += 1
        return {"message": {"content": self._response, "role": "assistant"}}


def make_evaluator(
    enabled: bool = True,
    threshold: float = 0.5,
    min_fragments: int = 2,
    question_detect: bool = True,
    llm: Any = None,
) -> ResponseReadinessEvaluator:
    config = ResponseReadinessConfig(
        enabled=enabled,
        confidence_threshold=threshold,
        tier1_min_fragments=min_fragments,
        tier1_question_detect=question_detect,
    )
    return ResponseReadinessEvaluator(config=config, llm=llm)


class TestEvaluate:
    def test_disabled_always_ready(self) -> None:
        e = make_evaluator(enabled=False)
        r = e.evaluate(["hello"])
        assert r.ready is True
        assert r.confidence == 1.0
        assert r.source == "tier1"

    def test_tier1_fragment_count_meets_threshold(self) -> None:
        e = make_evaluator(threshold=0.5, min_fragments=2)
        r = e.evaluate(["a", "b"])
        assert r.ready is True
        assert r.confidence >= 0.5
        assert r.source == "tier1"

    def test_tier1_fragment_count_below_threshold(self) -> None:
        e = make_evaluator(threshold=0.5, min_fragments=2)
        r = e.evaluate(["a"])
        assert r.ready is False
        assert r.confidence < 0.5

    def test_tier1_question_detected(self) -> None:
        e = make_evaluator(threshold=0.3, min_fragments=1)
        r = e.evaluate(["hello?"])
        assert r.ready is True

    def test_tier1_question_not_detected(self) -> None:
        e = make_evaluator(threshold=0.5, min_fragments=10, question_detect=False)
        r = e.evaluate(["hello?"])
        assert r.ready is False

    def test_tier1_confidence_below_threshold_triggers_tier2_with_llm(self) -> None:
        llm = FakeLLMBridge(response="Yes")
        e = make_evaluator(threshold=0.8, min_fragments=99, llm=llm)
        r = e.evaluate(["hello"])
        assert llm.call_count == 1
        assert r.source == "tier2"

    def test_tier2_llm_returns_yes(self) -> None:
        llm = FakeLLMBridge(response="Yes")
        e = make_evaluator(threshold=0.8, min_fragments=99, llm=llm)
        r = e.evaluate(["hello"])
        assert r.ready is True
        assert r.confidence == 0.8

    def test_tier2_llm_returns_no(self) -> None:
        llm = FakeLLMBridge(response="No")
        e = make_evaluator(threshold=0.8, min_fragments=99, llm=llm)
        r = e.evaluate(["hello"])
        assert r.ready is False
        assert r.confidence == 0.3

    def test_tier2_fallback_when_no_llm(self) -> None:
        e = make_evaluator(threshold=0.8, min_fragments=99, llm=None)
        r = e.evaluate(["hello"])
        assert r.source == "tier1"
        assert r.ready is False

    def test_confidence_clamped_to_max_1_0(self) -> None:
        e = make_evaluator(threshold=0.0, min_fragments=1, question_detect=True)
        r = e.evaluate(["hello? with lots of fragments a b c d e f g"])
        assert r.confidence <= 1.0
