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

LLMプロバイダ、ストアバックエンド、ベクトルDBなど、既存Pluginの交換部品を追加するときに読む。
サブプラグインは PluginManager のライフサイクル管理外。親Pluginの規約に従って発見・登録される。

## LLM Provider 現行方式

`iris/llm/providers/` の LLM Provider は `BaseLLMProvider` 継承クラスを自動発見する。
`provider_name` を設定すると `__init_subclass__` で自動登録されるため、通常はファイル追加だけでよい。

```
iris/llm/providers/
├── __init__.py              # discover_providers() を呼ぶ
├── base.py                  # BaseLLMProvider + registry
├── ollama.py
├── openai_compatible.py
└── new_provider.py          # 追加するファイル
```

## Steps

### 1. Providerクラスを作成する

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

### 2. 接続デフォルトを追加する（必要な場合）

`config.yaml` 側で `model.providers.<provider>.base_url` を必須にするなら不要。
デフォルトURLを持たせる場合は `iris/llm/model_factory.py` の `_PROVIDER_DEFAULTS` に追加する。

```python
_PROVIDER_DEFAULTS: dict[str, str] = {
    "new_provider": "https://api.example.com/v1",
}
```

### 3. 複数provider名を1クラスで扱う場合

`OpenAICompatibleProvider` のように1クラスを複数名へ割り当てる場合だけ、`iris/llm/providers/__init__.py` に明示登録を追加する。

```python
from .new_provider import NewProvider

register_provider("new_provider_alias", NewProvider)
```

公開APIとして外部importさせる必要がある場合のみ `__all__` も更新する。

### 4. テストを追加する

```python
def test_new_provider_build_call_kwargs() -> None:
    provider = NewProvider()
    kwargs = provider.build_call_kwargs(temperature=0.2, max_tokens=128, entry=None, kwargs={})
    assert kwargs
```

## Other Sub-plugins

LLM Provider以外は親Pluginごとの規約を確認する。

| 親Plugin | ディレクトリ | 発見・登録 |
|---|---|---|
| `llm` | `iris/llm/providers/` | `BaseLLMProvider.provider_name` による自動登録 |
| `tools` | `iris/tools/builtins/` | ToolRegistry が builtins を読み込み、`register(registry)` / decorator を登録 |
| `memory` | 未固定 | 追加時に親Plugin側の規約を先に設計 |

## Rules

- PluginManager の `MANIFEST` は持たない。親Pluginが責任を持つ
- LLM Provider は `BaseLLMProvider` を継承し、`provider_name` を `config.yaml` の `models[].provider` と一致させる
- `create_chat_model()` と `build_call_kwargs()` を必ず実装する
- `_` で始まる provider ファイルは自動発見されない
- 既存の `discover_sub_plugins()` 前提で手順を書かない。親Pluginの現行発見方式を実コードで確認する
