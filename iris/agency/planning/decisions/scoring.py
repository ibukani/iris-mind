from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from iris.kernel.config import ProactiveConfig

if TYPE_CHECKING:
    from iris.limbic.models import DriveState, EmotionState
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
    last_proactive_time: float = 0.0
    last_user_activity: float = 0.0
    negative_mood_score: float = 0.0
    limbic_mood: EmotionState | None = None
    limbic_drive: DriveState | None = None
    content: str = ""
    context: dict[str, Any] | None = None
    ignore_count: int = 0


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

    def compute(self, ctx: ScoreContext) -> tuple[float, dict[str, float]]:
        time_score = self._compute_time_score(ctx.now, ctx.last_proactive_time, ctx.last_user_activity)
        memory_score = self._compute_memory_score()
        context_score = self._compute_context_score()
        mood_score = self._compute_mood_score(ctx.negative_mood_score, ctx.limbic_mood)
        drive_score = self._compute_drive_score(ctx.limbic_drive)
        sensory_score = self._compute_sensory_score()
        stm_score = self._compute_short_term_score()
        urgency_score = self._compute_content_urgency(ctx.content)
        context_score = max(context_score, stm_score) if stm_score > 0 else context_score

        mood_weight = self._compute_mood_weight(ctx.limbic_mood)
        total, ignore_penalty = self._aggregate_scores(
            time_score,
            memory_score,
            context_score,
            mood_score,
            mood_weight,
            drive_score,
            sensory_score,
            urgency_score,
            ctx.ignore_count,
            ctx.context,
        )

        logger.debug(
            "Scores: time={:.3f} mem={:.3f} ctx={:.3f} mood={:.3f} sensory={:.3f} stm={:.3f} urg={:.3f} "
            "ignore={} total={:.3f} (threshold={:.2f})",
            time_score,
            memory_score,
            context_score,
            mood_score,
            sensory_score,
            stm_score,
            urgency_score,
            ctx.ignore_count,
            total,
            self._config.speak_threshold,
        )
        return total, {
            "time": time_score,
            "memory": memory_score,
            "context": context_score,
            "mood": mood_score,
            "drive": drive_score,
            "sensory": sensory_score,
            "short_term": stm_score,
            "urgency": urgency_score,
            "ignore_penalty": ignore_penalty if ctx.ignore_count > 0 else 1.0,
        }

    @staticmethod
    def _compute_mood_weight(limbic_mood: EmotionState | None) -> float:
        if not limbic_mood:
            return 0.15
        v = limbic_mood.valence
        a = limbic_mood.arousal
        d = limbic_mood.dominance
        intensity = abs(v) * 0.5 + a * 0.3 + abs(d - 0.5) * 0.2
        return 0.10 + intensity * 0.25

    def _aggregate_scores(
        self,
        time_score: float,
        memory_score: float,
        context_score: float,
        mood_score: float,
        mood_weight: float,
        drive_score: float,
        sensory_score: float,
        urgency_score: float,
        ignore_count: int,
        context: dict[str, Any] | None,
    ) -> tuple[float, float]:
        w = self._config.trigger_weights
        total = (
            w.get("time", 0.25) * time_score
            + w.get("memory", 0.45) * memory_score
            + w.get("context", 0.15) * context_score
            + mood_weight * mood_score
            + w.get("drive", 0.20) * drive_score
        )
        if sensory_score > 0:
            total = max(total, sensory_score * 0.3)
        total = max(total, urgency_score * 0.15)

        ignore_penalty = 1.0
        if ignore_count > 0:
            ignore_penalty = max(0.2, 1.0 - ignore_count * 0.25)
            total *= ignore_penalty

        if context and context.get("system_event") == "connected":
            total = max(total, self._config.speak_threshold + 0.1)
        return total, ignore_penalty

    def _compute_time_score(self, now: float, last_proactive_time: float, last_user_activity: float) -> float:
        last_time = max(last_proactive_time, last_user_activity)
        if last_time == 0:
            return 0.0
        elapsed = now - last_time

        if last_user_activity > 0:
            elapsed_since_user = now - last_user_activity
            if elapsed_since_user < 60.0:
                return 1.0

        if elapsed < self._config.min_interval_sec:
            return 0.0
        ratio = (elapsed - self._config.min_interval_sec) / (
            self._config.max_interval_sec - self._config.min_interval_sec
        )
        return min(ratio, 1.0)

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

    @staticmethod
    def _compute_mood_score(negative_mood_score: float, limbic_mood: EmotionState | None = None) -> float:
        if limbic_mood:
            valence = limbic_mood.valence
            arousal = limbic_mood.arousal
            dominance = limbic_mood.dominance

            mood_valence = valence * 0.5 if valence > 0 else valence * 1.5

            mood_arousal = 0.6 if arousal > 0.6 else (0.3 if arousal < 0.15 else 0.4)
            mood_dominance = dominance * 0.4

            return max(0.0, min(1.0, mood_valence + mood_arousal + mood_dominance))

        if negative_mood_score >= 0.7:
            return 0.0
        return max(0.0, 1.0 - negative_mood_score)

    @staticmethod
    def _compute_drive_score(limbic_drive: DriveState | None) -> float:
        if not limbic_drive:
            return 0.0
        return max(limbic_drive.curiosity, limbic_drive.social_need, limbic_drive.maintenance)
