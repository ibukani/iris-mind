from __future__ import annotations

from typing import Any

from loguru import logger

from .appraiser import Appraiser
from .generator import EmotionGenerator
from .models import AppraisalDimensions, CompanionEmotion, EmotionResult
from .mood import MoodDynamics
from .relationship import RelationshipManager
from .state import EmotionStateManager


class LimbicOrchestrator:
    """Appraisal → Emotion → Relationship パイプライン統合"""

    def __init__(self) -> None:
        self._appraiser = Appraiser()
        self._generator = EmotionGenerator()
        self._mood = MoodDynamics()
        self._relationship = RelationshipManager()
        self._state = EmotionStateManager()

    def process(
        self,
        text: str,
        context: dict[str, Any] | None = None,
        user_profile: dict[str, Any] | None = None,
    ) -> EmotionResult:
        """メインパイプライン: テキスト → 感情 + 関係性更新"""
        ctx = context or {}
        profile = user_profile or self._relationship.get_profile()

        primary = self._appraiser.appraise_primary(text, ctx)
        secondary = self._appraiser.appraise_secondary(primary, profile)
        context_type = self._appraiser.detect_context_type(text)

        dimensions = self._appraiser.compute_dimensions(primary, secondary)

        current_mood = self._mood.get_mood()
        emotion = self._generator.generate(dimensions, current_mood)

        updated_mood = self._mood.update(emotion)
        relationship = self._relationship.update(emotion, context_type, profile)

        reappraisal_needed = self._check_reappraisal_needed(dimensions, emotion)
        reappraisal_suggestion = ""
        if reappraisal_needed:
            reappraisal_suggestion = self._suggest_reappraisal(dimensions, emotion)

        result = EmotionResult(
            appraisal=dimensions,
            emotion=emotion,
            mood=updated_mood,
            relationship=relationship,
            reappraisal_needed=reappraisal_needed,
            reappraisal_suggestion=reappraisal_suggestion,
        )
        self._state.update(result)

        logger.debug(
            "Limbic: emotion={} intensity={:.2f} trust={:.2f} level={}",
            emotion.primary.value,
            emotion.intensity,
            relationship.trust,
            relationship.level.name,
        )

        return result

    def get_state(self) -> dict[str, Any]:
        return self._state.get_state()

    def get_emotion_for_prompt(self) -> dict[str, Any]:
        return self._state.get_emotion_for_prompt()

    def get_relationship_profile(self) -> dict[str, Any]:
        return self._relationship.get_profile()

    def _check_reappraisal_needed(self, dimensions: AppraisalDimensions, emotion: CompanionEmotion) -> bool:
        return (emotion.primary.value in ("anger", "fear", "disgust") and emotion.intensity > 0.6) or (
            dimensions.unpleasantness > 0.7 and dimensions.control < 0.3
        )

    def _suggest_reappraisal(self, dimensions: AppraisalDimensions, emotion: CompanionEmotion) -> str:
        suggestions = {
            "anger": "相手の意図を再確認し、別の解釈を試みてみる",
            "fear": "最悪のシナリオを具体的に書き出し、対策を立てる",
            "disgust": "状況を一歩引いて観察し、学びとして捉え直す",
        }
        return suggestions.get(emotion.primary.value, "状況を客観的に再評価してみる")
