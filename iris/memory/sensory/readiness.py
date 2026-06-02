from __future__ import annotations

import re

_QUESTION_RE = re.compile(r"[？?]$")


class ReadinessEvaluator:
    """Tier1 ルールベース評価のみ行う ReadinessEvaluator。

    Tier2 (LLM による評価) は削除された。必要な場合は非同期版を別途設計すること。
    """

    def __init__(
        self,
        min_fragments: int = 2,
        question_detect: bool = True,
        confidence_threshold: float = 0.6,
    ) -> None:
        self._min_fragments = min_fragments
        self._question_detect = question_detect
        self._confidence_threshold = confidence_threshold

    def evaluate(self, fragments: list[str], is_final: bool) -> bool:
        if is_final:
            return True
        if len(fragments) < self._min_fragments:
            return False

        score = self._tier1_score(fragments)
        return score >= self._confidence_threshold

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
