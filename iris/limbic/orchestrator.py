from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from .appraiser import Appraiser
from .generator import EmotionGenerator
from .models import AppraisalDimensions, CompanionEmotion, EmotionResult
from .mood import MoodDynamics
from .relationship import RelationshipManager
from .state import EmotionStateManager

if TYPE_CHECKING:
    from iris.account.manager import AccountManager
    from iris.room.manager import RoomManager


class LimbicOrchestrator:
    """Appraisal → Emotion → Relationship パイプライン統合"""

    def __init__(
        self,
        account_manager: AccountManager | None = None,
        room_manager: RoomManager | None = None,
    ) -> None:
        self._appraiser = Appraiser()
        self._generator = EmotionGenerator()
        self._mood = MoodDynamics()
        self._relationship = RelationshipManager()
        self._state = EmotionStateManager()
        self._account_manager = account_manager
        self._room_manager = room_manager

    def process(
        self,
        text: str,
        context: dict[str, Any] | None = None,
        user_profile: dict[str, Any] | None = None,
        account_id: str = "",
    ) -> EmotionResult:
        """メインパイプライン: テキスト → 感情 + 関係性更新"""
        ctx = self._enrich_context(context, account_id)
        profile = user_profile or self._relationship.get_profile(account_id)

        primary = self._appraiser.appraise_primary(text, ctx)
        secondary = self._appraiser.appraise_secondary(primary, profile)
        context_type = self._appraiser.detect_context_type(text)

        dimensions = self._appraiser.compute_dimensions(primary, secondary)

        current_mood = self._mood.get_mood()
        emotion = self._generator.generate(dimensions, current_mood)

        updated_mood = self._mood.update(emotion)
        relationship = self._relationship.update(emotion, account_id, context_type, profile)

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
            "Limbic: emotion={} intensity={:.2f} trust={:.2f} level={} account={}",
            emotion.primary.value,
            emotion.intensity,
            relationship.trust,
            relationship.level.name,
            account_id or "(global)",
        )

        return result

    def _enrich_context(
        self,
        context: dict[str, Any] | None,
        account_id: str,
    ) -> dict[str, Any]:
        """AccountManager/RoomManager から context dict を補完"""
        ctx = dict(context) if context else {}

        if self._account_manager and account_id:
            account = self._account_manager.resolve(account_id)
            if account:
                ctx.setdefault("display_name", account.display_name)
                ctx.setdefault("account_created", account.created_at)

        room_id = ctx.get("room_id", "")
        if self._room_manager and room_id:
            room = self._room_manager.get_room(room_id)
            if room:
                ctx.setdefault("room_name", room.name)
                ctx.setdefault("room_topic", room.topic)
                members = self._room_manager.get_members(room_id)
                ctx.setdefault("member_count", len(members))

        return ctx

    def get_state(self) -> dict[str, Any]:
        return self._state.get_state()

    def get_emotion_for_prompt(self, account_id: str = "") -> dict[str, Any]:
        return self._state.get_emotion_for_prompt()

    def get_relationship_profile(self, account_id: str = "") -> dict[str, Any]:
        return self._relationship.get_profile(account_id)

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
