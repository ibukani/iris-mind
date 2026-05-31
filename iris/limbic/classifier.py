from __future__ import annotations

from collections.abc import Callable
import importlib
from typing import Any

from .models import PlutchikEmotion

DEFAULT_EMOTION_MODEL = "koshin2001/Japanese-to-emotions"

_LABEL_MAP: dict[str, str] = {
    "joy": PlutchikEmotion.JOY.value,
    "happy": PlutchikEmotion.JOY.value,
    "happiness": PlutchikEmotion.JOY.value,
    "喜び": PlutchikEmotion.JOY.value,
    "嬉しい": PlutchikEmotion.JOY.value,
    "sadness": PlutchikEmotion.SADNESS.value,
    "sad": PlutchikEmotion.SADNESS.value,
    "悲しみ": PlutchikEmotion.SADNESS.value,
    "anger": PlutchikEmotion.ANGER.value,
    "angry": PlutchikEmotion.ANGER.value,
    "怒り": PlutchikEmotion.ANGER.value,
    "fear": PlutchikEmotion.FEAR.value,
    "怖れ": PlutchikEmotion.FEAR.value,
    "恐れ": PlutchikEmotion.FEAR.value,
    "surprise": PlutchikEmotion.SURPRISE.value,
    "surprised": PlutchikEmotion.SURPRISE.value,
    "驚き": PlutchikEmotion.SURPRISE.value,
    "disgust": PlutchikEmotion.DISGUST.value,
    "嫌悪": PlutchikEmotion.DISGUST.value,
    "trust": PlutchikEmotion.TRUST.value,
    "信頼": PlutchikEmotion.TRUST.value,
    "anticipation": PlutchikEmotion.ANTICIPATION.value,
    "期待": PlutchikEmotion.ANTICIPATION.value,
}


class NeuralEmotionClassifier:
    """MiniLM/BERT ベースの感情分類モデル。"""

    def __init__(
        self,
        model_name: str = DEFAULT_EMOTION_MODEL,
        *,
        pipeline_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._model_name = model_name or DEFAULT_EMOTION_MODEL
        self._pipeline_factory = pipeline_factory
        self._pipeline: Callable[[str], object] | None = None

    def classify(self, text: str) -> dict[str, float]:
        if not text.strip():
            return {}
        self._load_model()
        if self._pipeline is None:
            return {}
        results = self._pipeline(text)
        return self._map_to_plutchik(results)

    def _load_model(self) -> None:
        if self._pipeline is not None:
            return
        pipeline_factory = self._pipeline_factory
        if pipeline_factory is not None:
            self._pipeline = pipeline_factory()
            return
        try:
            transformers = importlib.import_module("transformers")
        except ImportError as exc:
            raise RuntimeError(
                "Neural emotion classifier requires optional dependency: "
                "install iris-mind[emotion] and a transformers backend such as torch."
            ) from exc

        pipeline = transformers.pipeline
        self._pipeline = pipeline(
            "text-classification",
            model=self._model_name,
            top_k=None,
            function_to_apply="sigmoid",
        )

    def _map_to_plutchik(self, results: object) -> dict[str, float]:
        items = self._flatten_results(results)
        scores: dict[str, float] = {}
        for item in items:
            label = str(item.get("label", "")).strip().lower()
            emotion = _LABEL_MAP.get(label)
            score = item.get("score")
            if emotion is None or not isinstance(score, int | float):
                continue
            scores[emotion] = max(0.0, min(1.0, float(score)))
        return scores

    def _flatten_results(self, results: object) -> list[dict[str, object]]:
        if not isinstance(results, list):
            return []
        if results and isinstance(results[0], list):
            nested = results[0]
            return [item for item in nested if isinstance(item, dict)]
        return [item for item in results if isinstance(item, dict)]
