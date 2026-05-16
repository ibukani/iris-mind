from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from iris.kernel.config import ResponseReadinessConfig
from iris.llm.llm_bridge import LLMBridge

logger = logging.getLogger(__name__)


_QUESTION_RE = re.compile(r"[？?]$")


@dataclass
class ReadinessResult:
    ready: bool
    confidence: float
    source: str  # "tier1" | "tier2"


class ResponseReadinessEvaluator:
    def __init__(
        self,
        config: ResponseReadinessConfig,
        llm: LLMBridge | None = None,
    ) -> None:
        self._config = config
        self._llm = llm

    def evaluate(self, fragments: list[str], model_role: str = "fast") -> ReadinessResult:
        if not self._config.enabled:
            return ReadinessResult(ready=True, confidence=1.0, source="tier1")

        tier1 = self._evaluate_tier1(fragments)
        if tier1.confidence >= self._config.confidence_threshold:
            return tier1

        if self._llm is None:
            return tier1

        return self._evaluate_tier2(fragments, model_role)

    def _evaluate_tier1(self, fragments: list[str]) -> ReadinessResult:
        score = 0.0
        reasons: list[str] = []

        min_frags = self._config.tier1_min_fragments
        if len(fragments) >= min_frags:
            score += 0.4
            reasons.append(f"fragment_count>={min_frags}")

        last = fragments[-1] if fragments else ""
        if self._config.tier1_question_detect and _QUESTION_RE.search(last):
            score += 0.4
            reasons.append("question_detected")

        if any(f.strip() for f in fragments):
            score += 0.2

        ready = score >= self._config.confidence_threshold
        return ReadinessResult(ready=ready, confidence=min(score, 1.0), source="tier1")

    def _evaluate_tier2(self, fragments: list[str], model_role: str = "fast") -> ReadinessResult:
        if self._llm is None:
            return ReadinessResult(ready=False, confidence=0.0, source="tier2")

        text = " ".join(fragments)
        prompt = (
            "You are evaluating a conversation fragment.\n"
            f"User said: {text}\n\n"
            "Can you respond meaningfully right now? Answer Yes or No.\n"
            "If the user's input is a question, complete thought, or continuation of conversation, answer Yes."
        )

        try:
            resp = self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model_role,
                temperature=0.0,
                max_tokens=10,
            )
            content = resp.get("message", {}).get("content", "").strip().lower()
            ready = content.startswith("yes")
            return ReadinessResult(ready=ready, confidence=0.8 if ready else 0.3, source="tier2")
        except Exception:
            logger.exception("Tier2 readiness evaluation failed")
            return ReadinessResult(ready=False, confidence=0.0, source="tier2")
