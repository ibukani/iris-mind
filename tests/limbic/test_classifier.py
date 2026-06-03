from __future__ import annotations

import sys

import pytest

from iris.limbic.classifier import NeuralEmotionClassifier

pytestmark = pytest.mark.legacy


class _FakePipeline:
    def __init__(self, results: object) -> None:
        self._results = results

    def __call__(self, text: str) -> object:
        return self._results


def test_classify_maps_pipeline_labels() -> None:
    classifier = NeuralEmotionClassifier(
        pipeline_factory=lambda: _FakePipeline(
            [
                {"label": "joy", "score": 0.8},
                {"label": "sadness", "score": 0.2},
                {"label": "unknown", "score": 0.9},
            ],
        ),
    )

    assert classifier.classify("嬉しい") == {"joy": 0.8, "sadness": 0.2}


def test_classify_maps_nested_pipeline_result() -> None:
    classifier = NeuralEmotionClassifier(
        pipeline_factory=lambda: _FakePipeline(
            [
                [
                    {"label": "anger", "score": 1.2},
                    {"label": "fear", "score": -0.1},
                ],
            ],
        ),
    )

    assert classifier.classify("怖い") == {"anger": 1.0, "fear": 0.0}


def test_classify_empty_text_skips_model_load() -> None:
    classifier = NeuralEmotionClassifier(
        pipeline_factory=lambda: pytest.fail("pipeline should not load"),
    )

    assert classifier.classify("  ") == {}


def test_missing_transformers_reports_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "transformers", None)
    classifier = NeuralEmotionClassifier()

    with pytest.raises(RuntimeError, match="iris-mind\\[emotion\\]"):
        classifier.classify("嬉しい")


def test_preload_forces_model_load() -> None:
    load_count = 0

    def _factory() -> _FakePipeline:
        nonlocal load_count
        load_count += 1
        return _FakePipeline([{"label": "joy", "score": 0.9}])

    classifier = NeuralEmotionClassifier(pipeline_factory=_factory)
    classifier.preload()

    assert load_count == 1
    assert classifier.classify("嬉しい") == {"joy": 0.9}
    assert load_count == 1


def test_preload_idempotent() -> None:
    load_count = 0

    def _factory() -> _FakePipeline:
        nonlocal load_count
        load_count += 1
        return _FakePipeline([{"label": "joy", "score": 0.9}])

    classifier = NeuralEmotionClassifier(pipeline_factory=_factory)
    classifier.preload()
    classifier.preload()

    assert load_count == 1


def test_device_stored() -> None:
    classifier = NeuralEmotionClassifier(device="cuda:0")
    assert classifier._device == "cuda:0"
