from __future__ import annotations

import logging

from iris.kernel.config import ProactiveConfig
from iris.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class ProactiveScoring:
    """PFC が自発発話の価値を評価するスコアリング。

    脳: 前頭前野 (PFC) の背外側部 (dlPFC) が環境と内部状態を統合し、
    「今、自発的に行動を起こす価値があるか」を判断する処理に対応する。

    4つの因子を重み付け統合:
    - time: 前回の行動からの経過時間
    - memory: 長期記憶との関連性（新奇性＋既存知識との接続）
    - context: 直近会話の文脈的一貫性
    - mood: 感情状態（扁桃体からの入力を受けた値）
    """

    def __init__(self, config: ProactiveConfig, memory: MemoryManager) -> None:
        self._config = config
        self._memory = memory

    def compute(
        self,
        now: float,
        last_proactive_time: float,
        last_user_activity: float,
        negative_mood_score: float,
        limbic_mood: dict[str, float] | None = None,
        content: str = "",
    ) -> tuple[float, dict[str, float]]:
        w = self._config.trigger_weights
        time_score = self._compute_time_score(now, last_proactive_time, last_user_activity)
        memory_score = self._compute_memory_score()
        context_score = self._compute_context_score()
        mood_score = self._compute_mood_score(negative_mood_score, limbic_mood)
        sensory_score = self._compute_sensory_score()
        stm_score = self._compute_short_term_score()
        urgency_score = self._compute_content_urgency(content)
        context_score = max(context_score, stm_score) if stm_score > 0 else context_score
        total = (
            w.get("time", 0.25) * time_score
            + w.get("memory", 0.45) * memory_score
            + w.get("context", 0.15) * context_score
            + w.get("mood", 0.15) * mood_score
        )
        if sensory_score > 0:
            total = max(total, sensory_score * 0.3)
        total = max(total, urgency_score * 0.15)
        logger.debug(
            "Scores: time=%.3f mem=%.3f ctx=%.3f mood=%.3f sensory=%.3f stm=%.3f urg=%.3f total=%.3f (threshold=%.2f)",
            time_score,
            memory_score,
            context_score,
            mood_score,
            sensory_score,
            stm_score,
            urgency_score,
            total,
            self._config.speak_threshold,
        )
        return total, {
            "time": time_score,
            "memory": memory_score,
            "context": context_score,
            "mood": mood_score,
            "sensory": sensory_score,
            "short_term": stm_score,
            "urgency": urgency_score,
        }

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
                return max(r.get("score", 0.0) for r in results)  # type: ignore[no-any-return]
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

    def _compute_sensory_score(self) -> float:
        try:
            sensory = self._memory.sensory.retrieve()
            if sensory.get("raw"):
                return 0.6
        except Exception:
            pass
        return 0.0

    def _compute_short_term_score(self) -> float:
        try:
            turns = self._memory.short_term.get_recent_turns(2)
            if len(turns) >= 2:
                return 0.5
            if len(turns) == 1:
                return 0.3
        except Exception:
            pass
        return 0.0

    @staticmethod
    def _compute_content_urgency(content: str) -> float:
        if not content:
            return 0.0
        score = 0.0
        lower = content.lower()
        if any(q in content for q in ["？", "?", "教えて", "what", "how", "why"]):
            score += 0.3
        if any(w in lower for w in ["urgent", "important", "急", "至急", "help", "問題"]):
            score += 0.3
        if len(content) > 100:
            score += 0.2
        if content.count("!") >= 2:
            score += 0.1
        return min(score, 0.8)

    @staticmethod
    def _compute_mood_score(negative_mood_score: float, limbic_mood: dict[str, float] | None = None) -> float:
        if limbic_mood:
            valence = limbic_mood.get("valence", 0.0)
            arousal = limbic_mood.get("arousal", 0.0)
            dominance = limbic_mood.get("dominance", 0.0)

            mood_valence = max(0.0, valence)
            mood_arousal = 0.6 if arousal > 0.6 else (0.3 if arousal < 0.15 else 0.4)
            mood_dominance = dominance * 0.4

            return min(1.0, mood_valence * 0.5 + mood_arousal + mood_dominance)

        if negative_mood_score >= 0.7:
            return 0.0
        return max(0.0, 1.0 - negative_mood_score)
