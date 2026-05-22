from unittest.mock import MagicMock, patch

import httpx
import pytest

from iris.kernel.config import ModelConfig, ModelEntry, ProviderConnection
from iris.llm.providers import GoogleProvider


def test_google_provider_init_error():
    with pytest.raises(ValueError, match="api_key is required"):
        GoogleProvider(api_key="")


def test_google_provider_is_available():
    provider = GoogleProvider(api_key="test_key")
    assert provider.is_available() is True


def test_google_provider_chat_success():
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"role": "assistant", "content": "Hello world"}}]}

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.post.return_value = mock_response

    provider = GoogleProvider(api_key="test_key", http_client=mock_client)
    import asyncio

    res = asyncio.run(provider.chat(messages=[{"role": "user", "content": "Hi"}], model="gemini-2.5-flash"))

    assert res["message"]["content"] == "Hello world"
    mock_client.post.assert_called_once()
    _, kwargs = mock_client.post.call_args
    assert kwargs["json"]["model"] == "gemini-2.5-flash"
    assert kwargs["json"]["stream"] is False


def test_google_provider_chat_stream_success():
    mock_stream = MagicMock()
    mock_stream.status_code = 200
    mock_stream.iter_lines.return_value = [
        'data: {"choices": [{"delta": {"content": "Hello"}}]}',
        'data: {"choices": [{"delta": {"content": " world"}}]}',
        "data: [DONE]",
    ]

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.stream.return_value.__enter__.return_value = mock_stream

    provider = GoogleProvider(api_key="test_key", http_client=mock_client)

    tokens = []

    def on_token(t: str):
        tokens.append(t)

    import asyncio

    res = asyncio.run(
        provider.chat(messages=[{"role": "user", "content": "Hi"}], model="gemini-2.5-flash", on_token=on_token)
    )

    assert "".join(tokens) == "Hello world"
    assert res["message"]["content"] == "Hello world"


def test_google_provider_ensure_environment_success():
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": [{"id": "gemini-2.5-flash"}, {"id": "gemini-2.0-flash"}]}

    with patch("httpx.get", return_value=mock_response) as mock_get:
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
        mock_get.assert_called_once()


def test_google_provider_ensure_environment_api_key_missing():
    entries = [ModelEntry(name="gemini-2.5-flash", provider="google")]
    model_config = ModelConfig(
        models=entries,
        providers={"google": ProviderConnection()},
    )
    res = GoogleProvider.ensure_environment(entries, model_config)
    assert res is False


def test_google_provider_ensure_environment_fail():
    with patch("httpx.get", side_effect=httpx.HTTPError("Connection error")) as mock_get:
        entries = [ModelEntry(name="gemini-2.5-flash", provider="google")]
        model_config = ModelConfig(
            models=entries,
            providers={"google": ProviderConnection(api_key="test_key")},
        )
        res = GoogleProvider.ensure_environment(entries, model_config)
        assert res is False
        mock_get.assert_called_once()
