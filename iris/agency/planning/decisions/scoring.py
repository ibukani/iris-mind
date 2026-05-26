from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from iris.kernel.config import ProactiveConfig

if TYPE_CHECKING:
    from iris.memory.manager import MemoryManager

from loguru import logger

_URGENCY_QUESTION = 0.3
_URGENCY_DEMANDING = 0.3
_URGENCY_LONG_CONTENT = 0.2
_URGENCY_EXCLAMATION = 0.1
_URGENCY_MAX = 0.8


def _safe_score(fn: Callable[[], float], default: float = 0.0) -> float:
    try:
        return fn()
    except Exception:
        logger.opt(exception=True).debug("Score computation failed")
        return default


@dataclass
class ScoreContext:
    now: float
    content: str = ""
    context: dict[str, Any] | None = None


class ProactiveScoring:
    def __init__(self, config: ProactiveConfig, memory: MemoryManager) -> None:
        self._config = config
        self._memory = memory

    def compute(self, ctx: ScoreContext) -> tuple[float, dict[str, float]]:
        memory_score = self._compute_memory_score()
        context_score = self._compute_context_score()
        sensory_score = self._compute_sensory_score()
        stm_score = self._compute_short_term_score()
        urgency_score = self._compute_content_urgency(ctx.content)
        context_score = max(context_score, stm_score) if stm_score > 0 else context_score

        total = self._aggregate_scores(memory_score, context_score, sensory_score, urgency_score, ctx.context)

        logger.debug(
            "Scores: mem={:.3f} ctx={:.3f} sensory={:.3f} stm={:.3f} urg={:.3f} total={:.3f} (threshold={:.2f})",
            memory_score,
            context_score,
            sensory_score,
            stm_score,
            urgency_score,
            total,
            self._config.speak_threshold,
        )
        return total, {
            "memory": memory_score,
            "context": context_score,
            "sensory": sensory_score,
            "short_term": stm_score,
            "urgency": urgency_score,
        }

    def _aggregate_scores(
        self,
        memory_score: float,
        context_score: float,
        sensory_score: float,
        urgency_score: float,
        context: dict[str, Any] | None,
    ) -> float:
        w = self._config.trigger_weights
        total = w.get("memory", 0.55) * memory_score + w.get("context", 0.30) * context_score
        if sensory_score > 0:
            total = max(total, sensory_score * 0.3)
        total = max(total, urgency_score * 0.15)

        if context and context.get("system_event") == "connected":
            total = max(total, self._config.speak_threshold + 0.1)

        return total

    def _compute_memory_score(self) -> float:
        return _safe_score(self._do_compute_memory_score, 0.0)

    def _do_compute_memory_score(self) -> float:
        recent = self._memory.get_recent(3)
        if not recent:
            return 0.0
        topic = " ".join(item.get("summary", "") for item in recent)
        if not topic.strip():
            return 0.0
        results = self._memory.search_semantic(topic, max_results=3)
        if results:
            return max(r.get("score", 0.0) for r in results)  # type: ignore[no-any-return]
        return 0.0

    @staticmethod
    def _char_bigram_set(text: str) -> set[str]:
        return {text[i : i + 2] for i in range(len(text) - 1)}

    def _compute_context_score(self) -> float:
        return _safe_score(self._do_compute_context_score, 0.0)

    def _do_compute_context_score(self) -> float:
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

    def _compute_sensory_score(self) -> float:
        return _safe_score(self._do_compute_sensory_score, 0.0)

    def _do_compute_sensory_score(self) -> float:
        sensory = self._memory.sensory.retrieve()
        return 0.6 if sensory.get("raw") else 0.0

    def _compute_short_term_score(self) -> float:
        return _safe_score(self._do_compute_short_term_score, 0.0)

    def _do_compute_short_term_score(self) -> float:
        turns = self._memory.short_term.get_recent_turns(2)
        if len(turns) >= 2:
            return 0.5
        if len(turns) == 1:
            return 0.3
        return 0.0

    @staticmethod
    def _compute_content_urgency(content: str) -> float:
        if not content:
            return 0.0
        score = 0.0
        lower = content.lower()
        if any(q in content for q in ["？", "?", "教えて", "what", "how", "why"]):
            score += _URGENCY_QUESTION
        if any(w in lower for w in ["urgent", "important", "急", "至急", "help", "問題"]):
            score += _URGENCY_DEMANDING
        if len(content) > 100:
            score += _URGENCY_LONG_CONTENT
        if content.count("!") >= 2:
            score += _URGENCY_EXCLAMATION
        return min(score, _URGENCY_MAX)
