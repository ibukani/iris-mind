from __future__ import annotations

import logging

from iris.kernel.config import ProactiveConfig
from iris.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class ProactiveScoring:
    def __init__(self, config: ProactiveConfig, memory: MemoryManager) -> None:
        self._config = config
        self._memory = memory

    def compute(
        self,
        now: float,
        last_proactive_time: float,
        last_user_activity: float,
        negative_mood_score: float,
    ) -> tuple[float, dict[str, float]]:
        w = self._config.trigger_weights
        time_score = self._compute_time_score(now, last_proactive_time, last_user_activity)
        memory_score = self._compute_memory_score()
        context_score = self._compute_context_score()
        mood_score = self._compute_mood_score(negative_mood_score)
        total = (
            w.get("time", 0.25) * time_score
            + w.get("memory", 0.45) * memory_score
            + w.get("context", 0.15) * context_score
            + w.get("mood", 0.15) * mood_score
        )
        return total, {"time": time_score, "memory": memory_score, "context": context_score, "mood": mood_score}

    def _compute_time_score(self, now: float, last_proactive_time: float, last_user_activity: float) -> float:
        last_time = max(last_proactive_time, last_user_activity)
        if last_time == 0:
            return 0.4
        elapsed = now - last_time
        if elapsed < self._config.min_interval_sec:
            return 0.0
        ratio = (elapsed - self._config.min_interval_sec) / (
            self._config.max_interval_sec - self._config.min_interval_sec
        )
        return min(ratio, 1.0)

    def _compute_memory_score(self) -> float:
        try:
            recent = self._memory.get_recent(3)
            if not recent:
                return 0.0
            topic = " ".join(item.get("summary", "") for item in recent)
            if not topic.strip():
                return 0.0
            results = self._memory.search_semantic(topic, max_results=3)
            if results:
                return max(r.get("score", 0.0) for r in results)
        except Exception as e:
            logger.debug("Memory score failed: %s", e)
        return 0.0

    @staticmethod
    def _char_bigram_set(text: str) -> set[str]:
        return {text[i : i + 2] for i in range(len(text) - 1)}

    def _compute_context_score(self) -> float:
        try:
            recent = self._memory.get_recent(2)
            if len(recent) < 2:
                return 0.3
            summaries = [item.get("summary", "") for item in recent[-2:]]
            if all(len(s.strip()) < 10 for s in summaries):
                return 0.7
            bg_a = self._char_bigram_set(summaries[0])
            bg_b = self._char_bigram_set(summaries[1])
            if not bg_a and not bg_b:
                return 0.5
            if not bg_a or not bg_b:
                return 0.3
            jaccard = len(bg_a & bg_b) / len(bg_a | bg_b)
            return min(jaccard + 0.2, 1.0)
        except Exception:
            return 0.0

    @staticmethod
    def _compute_mood_score(negative_mood_score: float) -> float:
        if negative_mood_score >= 0.7:
            return 0.0
        return max(0.0, 1.0 - negative_mood_score)
