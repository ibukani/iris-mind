---
name: iris-plugin-provider
description: |
  Use when: adding a new LLM provider, store backend, vector DB, or any swappable sub-plugin.
  Do NOT use: creating a new plugin, adding hooks, adding capabilities.
license: MIT
metadata:
  audience: developers
  workflow: iris-extension
---

## Purpose

Read this when adding a replaceable part of an existing Plugin, such as an LLM provider, store backend, or vector DB. Sub-plugins are outside `PluginManager` lifecycle management. They are discovered and registered according to the parent Plugin's conventions.

## Current LLM Provider Pattern

LLM providers under `iris/llm/providers/` are auto-discovered by finding subclasses of `BaseLLMProvider`. Setting `provider_name` registers the class through `__init_subclass__`, so adding a file is usually enough.

```text
iris/llm/providers/
├── __init__.py              # calls discover_providers()
├── base.py                  # BaseLLMProvider + registry
├── ollama.py
├── openai_compatible.py
└── new_provider.py          # new file
```

## Steps

### 1. Create the provider class

```python
from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel

from iris.kernel.config import ModelConfig, ModelEntry

from .base import BaseLLMProvider


class NewProvider(BaseLLMProvider):
    provider_name = "new_provider"

    def create_chat_model(
        self,
        entry: ModelEntry,
        base_url: str,
        api_key: str,
        model_config: ModelConfig,
    ) -> BaseChatModel:
        ...

    def build_call_kwargs(
        self,
        temperature: float,
        max_tokens: int,
        entry: ModelEntry | None,
        kwargs: dict[str, Any],
        reasoning: bool | None = None,
        default_num_ctx: int = 8192,
    ) -> dict[str, Any]:
        ...

    @classmethod
    def ensure_environment(
        cls,
        entries: list[ModelEntry],
        model_config: ModelConfig,
    ) -> bool:
        return True
```

### 2. Add connection defaults when needed

If `config.yaml` requires `model.providers.<provider>.base_url`, no default is needed. If a default URL is needed, add it to `_PROVIDER_DEFAULTS` in `iris/llm/model_factory.py`.

```python
_PROVIDER_DEFAULTS: dict[str, str] = {
    "new_provider": "https://api.example.com/v1",
}
```

### 3. Support multiple provider names with one class

Only when mapping multiple names to one class, as with `OpenAICompatibleProvider`, add explicit registration in `iris/llm/providers/__init__.py`.

```python
from .new_provider import NewProvider

register_provider("new_provider_alias", NewProvider)
```

Update `__all__` only when it must be imported as public API.

### 4. Add tests

```python
def test_new_provider_build_call_kwargs() -> None:
    provider = NewProvider()
    kwargs = provider.build_call_kwargs(temperature=0.2, max_tokens=128, entry=None, kwargs={})
    assert kwargs
```

## Other Sub-plugins

For sub-plugins other than LLM providers, inspect the parent Plugin's current convention first.

| Parent Plugin | Directory | Discovery / registration |
|---|---|---|
| `llm` | `iris/llm/providers/` | Auto-registration through `BaseLLMProvider.provider_name` |
| `tools` | `iris/tools/builtins/` | ToolRegistry loads builtins and registers `register(registry)` / decorators |
| `memory` | Not fixed | Design the parent Plugin convention first when adding one |

## Rules

- Do not create a `MANIFEST` for sub-plugins. The parent Plugin owns responsibility.
- LLM providers must inherit `BaseLLMProvider` and set `provider_name` to match `models[].provider` in `config.yaml`.
- Always implement `create_chat_model()` and `build_call_kwargs()`.
- Provider files starting with `_` are not auto-discovered.
- Do not assume an existing `discover_sub_plugins()` workflow. Confirm the parent Plugin's current discovery mechanism in code.
