from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_QUESTION_RE = re.compile(r"[？?]$")


class ReadinessEvaluator:
    def __init__(
        self,
        min_fragments: int = 2,
        question_detect: bool = True,
        confidence_threshold: float = 0.6,
        llm=None,
        llm_model_role: str = "fast",
    ) -> None:
        self._min_fragments = min_fragments
        self._question_detect = question_detect
        self._confidence_threshold = confidence_threshold
        self._llm = llm
        self._llm_model_role = llm_model_role

    def evaluate(self, fragments: list[str], is_final: bool) -> bool:
        if is_final:
            return True
        if len(fragments) < self._min_fragments:
            return False

        score = self._tier1_score(fragments)
        if score >= self._confidence_threshold:
            return True

        if self._llm is None:
            return False

        return self._tier2_check(fragments)

    def _tier1_score(self, fragments: list[str]) -> float:
        score = 0.0
        if len(fragments) >= self._min_fragments:
            score += 0.4
        last = fragments[-1] if fragments else ""
        if self._question_detect and _QUESTION_RE.search(last):
            score += 0.4
        if any(f.strip() for f in fragments):
            score += 0.2
        return min(score, 1.0)

    def _tier2_check(self, fragments: list[str]) -> bool:
        if self._llm is None:
            return False
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
                model=self._llm_model_role,
                temperature=0.0,
                max_tokens=10,
            )
            content = resp.get("message", {}).get("content", "").strip().lower()
            return content.startswith("yes")
        except Exception:
            logger.exception("Tier2 readiness evaluation failed")
            return False
