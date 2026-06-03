"""プロバイダ登録・環境検証テスト。"""

from __future__ import annotations

import pytest

from iris.kernel.config import ModelConfig, ModelEntry, ProviderConnection
from iris.llm.providers import GoogleProvider, OpenRouterProvider
from iris.llm.providers.base import BaseLLMProvider, get_provider_class
from iris.llm.providers.ollama import OllamaProvider

pytestmark = pytest.mark.legacy


def test_openrouter_provider_registered() -> None:
    cls = get_provider_class("openrouter")
    assert cls is OpenRouterProvider


def test_google_provider_registered() -> None:
    cls = get_provider_class("google")
    assert cls is GoogleProvider


def test_ollama_provider_registered() -> None:
    cls = get_provider_class("ollama")
    assert cls is OllamaProvider


def test_openrouter_inherits_openai_compatible() -> None:
    assert issubclass(OpenRouterProvider, BaseLLMProvider)


def test_google_inherits_openai_compatible() -> None:
    assert issubclass(GoogleProvider, BaseLLMProvider)


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unknown provider type"):
        get_provider_class("nonexistent_provider")


def test_ollama_validate_environment_sets_env() -> None:
    import os

    entries = [ModelEntry(name="test-model", provider="ollama")]
    model_config = ModelConfig(models=entries, default_num_gpu=50)
    result = OllamaProvider.validate_environment(entries, model_config)
    assert result is True
    assert os.environ.get("OLLAMA_GPU_LAYERS") == "50"
    assert os.environ.get("OLLAMA_FLASH_ATTENTION") == "1"


def test_google_validate_environment_success() -> None:
    entries = [
        ModelEntry(name="gemini-2.5-flash", provider="google"),
    ]
    model_config = ModelConfig(
        models=entries,
        providers={"google": ProviderConnection(api_key="test_key")},
    )
    assert GoogleProvider.validate_environment(entries, model_config) is True


def test_google_validate_environment_missing_key() -> None:
    entries = [ModelEntry(name="gemini-2.5-flash", provider="google")]
    model_config = ModelConfig(
        models=entries,
        providers={"google": ProviderConnection()},
    )
    assert GoogleProvider.validate_environment(entries, model_config) is False
