from __future__ import annotations

from typing import ClassVar

from .models import (
    PLUTCHIK_VAD,
    AppraisalDimensions,
    CompanionEmotion,
    Mood,
    PlutchikEmotion,
)


class EmotionGenerator:
    """Appraisal次元 → Plutchik 8基本感情への変換"""

    # Appraisal次元 → Plutchik感情の重みマッピング
    _DIMENSION_WEIGHTS: ClassVar[dict[str, dict[PlutchikEmotion, float]]] = {
        "unpleasantness": {
            PlutchikEmotion.SADNESS: 0.4,
            PlutchikEmotion.ANGER: 0.3,
            PlutchikEmotion.DISGUST: 0.2,
            PlutchikEmotion.FEAR: 0.1,
        },
        "control": {
            PlutchikEmotion.ANGER: 0.3,
            PlutchikEmotion.JOY: 0.2,
            PlutchikEmotion.TRUST: 0.3,
            PlutchikEmotion.FEAR: 0.2,
        },
        "responsibility": {
            PlutchikEmotion.ANGER: 0.3,
            PlutchikEmotion.DISGUST: 0.2,
            PlutchikEmotion.SADNESS: 0.2,
            PlutchikEmotion.TRUST: 0.3,
        },
        "certainty": {
            PlutchikEmotion.TRUST: 0.4,
            PlutchikEmotion.SURPRISE: 0.3,
            PlutchikEmotion.FEAR: 0.3,
        },
        "effort": {
            PlutchikEmotion.ANTICIPATION: 0.4,
            PlutchikEmotion.SADNESS: 0.3,
            PlutchikEmotion.JOY: 0.3,
        },
        "attention": {
            PlutchikEmotion.SURPRISE: 0.3,
            PlutchikEmotion.ANTICIPATION: 0.4,
            PlutchikEmotion.JOY: 0.3,
        },
    }

    def generate(
        self,
        appraisal: AppraisalDimensions,
        mood: Mood | None = None,
    ) -> CompanionEmotion:
        """Appraisal次元からPlutchik感情を生成"""
        scores = self._compute_emotion_scores(appraisal)
        sorted_emotions = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        if not sorted_emotions or sorted_emotions[0][1] <= 0:
            return CompanionEmotion(
                primary=PlutchikEmotion.TRUST,
                intensity=0.1,
                valence=mood.valence if mood else 0.0,
                arousal=mood.arousal if mood else 0.0,
                dominance=mood.dominance if mood else 0.0,
            )

        primary_emotion = sorted_emotions[0][0]
        primary_intensity = min(1.0, sorted_emotions[0][1])

        secondary_emotion = sorted_emotions[1][0] if len(sorted_emotions) > 1 else None
        secondary_intensity = min(1.0, sorted_emotions[1][1]) if secondary_emotion else 0.0

        base_vad = PLUTCHIK_VAD[primary_emotion]
        mood_weight = 0.3
        mood_val = mood.valence if mood else 0.0
        mood_aro = mood.arousal if mood else 0.0
        mood_dom = mood.dominance if mood else 0.0

        valence = base_vad[0] * (1 - mood_weight) + mood_val * mood_weight
        arousal = base_vad[1] * (1 - mood_weight) + mood_aro * mood_weight
        dominance = base_vad[2] * (1 - mood_weight) + mood_dom * mood_weight

        valence = max(-1.0, min(1.0, valence))
        arousal = max(-1.0, min(1.0, arousal))
        dominance = max(-1.0, min(1.0, dominance))

        return CompanionEmotion(
            primary=primary_emotion,
            intensity=primary_intensity,
            valence=valence,
            arousal=arousal,
            dominance=dominance,
            secondary=secondary_emotion,
            secondary_intensity=secondary_intensity,
        )

    def _compute_emotion_scores(self, appraisal: AppraisalDimensions) -> dict[PlutchikEmotion, float]:
        scores: dict[PlutchikEmotion, float] = dict.fromkeys(PlutchikEmotion, 0.0)
        dims = {
            "unpleasantness": appraisal.unpleasantness,
            "control": appraisal.control,
            "responsibility": appraisal.responsibility,
            "certainty": appraisal.certainty,
            "effort": appraisal.effort,
            "attention": appraisal.attention,
        }
        for dim_name, dim_value in dims.items():
            weights = self._DIMENSION_WEIGHTS.get(dim_name, {})
            for emotion, weight in weights.items():
                scores[emotion] += dim_value * weight
        return scores
