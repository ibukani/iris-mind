---
name: iris-plugin-provider
description: Iris LLMプロバイダ/ストア/VDB などのサブプラグイン追加ワークフロー
license: MIT
metadata:
  audience: developers
  workflow: iris-extension
---

## Purpose

LLM プロバイダ、ストアバックエンド、ベクトルDBなど、既存プラグインの交換部品（サブプラグイン）を追加するときに読む。

## サブプラグインとは

サブプラグインは PluginManager が直接管理しない、親プラグインが独自に発見・登録する交換部品。
Plugin 全体の MANIFEST は持たない。`register(parent)` 関数のみを提供する。

```
iris/llm/providers/
├── __init__.py         # register_providers(bridge) 集約
├── ollama.py
├── openrouter.py
└── google.py           # 追加するファイル
```

## Steps

### 1. サブプラグインファイルを作成する

```python
# iris/llm/providers/google.py
def register(bridge):
    """bridge にプロバイダを登録する"""
    bridge.register_provider("google", GoogleChatModel(...))
    bridge.register_environment_check(GoogleProvider.ensure_environment)
```

### 2. 親プラグインが自動発見する仕組みを確認する

親プラグインの `register()` で `discover_sub_plugins()` が呼ばれているか:

```python
# iris/llm/__init__.py - LlmPlugin.init()
for sub_module in discover_sub_plugins("iris/llm/providers"):
    register_fn = getattr(sub_module, "register", None)
    if register_fn is not None:
        register_fn(llm)  # llm = LLMBridge インスタンス
```

親プラグインが `discover_sub_plugins()` を使っていない場合:
1. 親プラグインに `discover_sub_plugins()` 呼び出しを追加する
2. または親プラグインの `register()` 内で手動 `import` + `register(parent)` を呼ぶ

### 3. サブプラグインの命名規則

| 親Plugin | サブプラグインディレクトリ | ファイル名 | registerシグネチャ |
|---|---|---|---|
| `llm` | `iris/llm/providers/` | `<provider>.py` | `register(bridge: LLMBridge)` |
| `tools` | `iris/tools/builtins/` | `<tool>/server.py` | `register(registry: ToolRegistry)` |
| `memory` | `iris/memory/stores/` (将来) | `<store>.py` | `register(stores: ...)` |

### 4. Provider 追加の完全な例

```python
# iris/llm/providers/new_provider.py
from iris.kernel.config import ModelConfig, ModelEntry

class NewProvider:
    @classmethod
    def ensure_environment(cls, entries, model_config):
        # 環境チェック（API key確認、接続確認など）
        ...

def register(bridge):
    bridge.register_provider_class("new_provider", NewProvider)
    # またはデフォルトURLの追加
    bridge.register_default_url("new_provider", "https://api.newprovider.com/v1")
```

### 5. プロバイダエクスポートを更新する

```python
# iris/llm/providers/__init__.py
from .new_provider import NewProvider

_PROVIDER_CLASSES["new_provider"] = NewProvider

__all__ = [
    ...,
    "NewProvider",
]
```

### 6. 環境チェックを main.py に追加する（任意）

`main.py` の `_check_environment()` が自動で全プロバイダをチェックする。
新しいプロバイダタイプが `config.yaml` の `models[].provider` に指定されていれば自動検出される。

### 7. テストを追加する

```python
# tests/llm/test_new_provider.py
def test_ensure_environment():
    provider = NewProvider()
    ...
```

## Rules

- サブプラグインは PluginManager のライフサイクル管理外。親Pluginが責任を持つ
- サブプラグインの `register()` シグネチャは親Plugin依存。引数は親側の規約に従う
- `_` で始まるファイルは自動発見されない
- `register` 関数がなければサブプラグインとして認識されない（無視される）
- プロバイダ追加時は `iris/llm/providers/__init__.py` の `_PROVIDER_CLASSES` と `__all__` も更新すること
