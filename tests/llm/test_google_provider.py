from iris.kernel.config import ModelConfig, ModelEntry, ProviderConnection
from iris.llm.providers import GoogleProvider


def test_google_provider_ensure_environment_success():
    entries = [
        ModelEntry(name="gemini-2.5-flash", provider="google"),
        ModelEntry(name="gemini-2.0-flash", provider="google"),
    ]
    model_config = ModelConfig(
        models=entries,
        providers={"google": ProviderConnection(api_key="test_key")},
    )

    res = GoogleProvider.ensure_environment(entries, model_config)
    assert res is True


def test_google_provider_ensure_environment_api_key_missing():
    entries = [ModelEntry(name="gemini-2.5-flash", provider="google")]
    model_config = ModelConfig(
        models=entries,
        providers={"google": ProviderConnection()},
    )
    res = GoogleProvider.ensure_environment(entries, model_config)
    assert res is False
