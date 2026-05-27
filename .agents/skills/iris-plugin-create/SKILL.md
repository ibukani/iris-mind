---
name: iris-plugin-create
description: Iris 新規プラグイン作成の定式化ワークフロー
license: MIT
compatibility: *
metadata:
  audience: developers
  workflow: iris-extension
---

## Purpose

Iris に新しいプラグイン（層/機能/ツール/プロバイダ）を追加するときに読む。
すべてのプラグインは `PluginProtocol` に準拠する。

## Plugin カテゴリ

| カテゴリ | Phase | 説明 | 例 |
|---|---|---|---|
| `CORE` | 10 | 必須インフラ層 | io, llm, tools |
| `LAYER` | 20 | 認知層 | memory |
| `COGNITIVE` | 30 | 高度認知 | agency |
| `FEATURE` | 40 | 機能拡張 | limbic |
| `PROVIDER` | - | 実装差し替え | (sub-plugin) |
| `TOOL` | 10 | ツール拡張 | (sub-plugin) |

## Steps

### 1. ディレクトリを作成する

```
iris/<plugin_name>/
├── __init__.py     # MANIFEST + プラグインクラス + plugin インスタンス
├── hooks.py        # 任意: register_hooks(manager)
├── events.py       # 任意: イベント購読 (manager.event_bus.subscribe)
├── models.py       # 任意: プラグイン固有の型
└── tools/          # 任意: @tool 定義 (TOOLカテゴリの場合)
    └── __init__.py
```

### 2. `__init__.py` を作成する

```python
from iris.kernel.plugin import PluginManifest, PluginProtocol

MANIFEST = PluginManifest(
    name="my_plugin",
    version="0.1.0",
    category=PluginCategory.FEATURE,
    phase=PluginPhase.FEATURE,
    dependencies={"EventBus", "LLMBridge"},  # 依存するPlugin名
    provides=["MyService"],
    description="プラグインの説明",
)

class MyPlugin:
    MANIFEST = MANIFEST

    def init(self, manager):
        """DI登録 + コンポーネント生成 + 配線 + Hook購読"""
        manager.register_manifest(MANIFEST)
        # resolve: 依存をDIから取得
        event_bus = manager.resolve("EventBus")
        # create + wire: 内部コンポーネント生成
        # provide: 他Plugin向けにDI登録
        manager.provide("MyService", instance)
        # hooks
        from .hooks import register_hooks
        register_hooks(manager)

    def start(self, manager):
        """バックグラウンド処理開始（任意）"""
        pass

    def stop(self, manager):
        """クリーンアップ（任意）"""
        pass

plugin = MyPlugin()
```

### 3. `hooks.py` を作成する（任意）

```python
def register_hooks(manager):
    hooks = manager.hook_registry

    def _my_hook(data):
        return data

    hooks.register("llm.before_chat", _my_hook, priority=500)
```

利用可能な HookPoint 一覧は `.agents/skills/iris-plugin-hook/SKILL.md` を参照。

### 4. `events.py` を作成する（任意）

```python
def subscribe_events(manager):
    bus = manager.event_bus
    bus.subscribe("MessageEvent", _on_message)
```

### 5. 依存を確認する

PluginManager が提供する標準サービス:

| サービス名 | 提供元 |
|---|---|
| `EventBus` | PluginManager（インフラ） |
| `HookRegistry` | PluginManager（インフラ） |
| `Config` | PluginManager（インフラ） |
| `PluginManager` | PluginManager（自己） |
| `IOManager` | io Plugin |
| `SessionManager` | io Plugin |
| `GrpcListener` | io Plugin |
| `LLMBridge` | llm Plugin |
| `Tokenizers` | llm Plugin |
| `DebugCapture` | llm Plugin |
| `CapabilityChecker` | llm Plugin |
| `MemoryManager` | memory Plugin |
| `SensoryMemoryManager` | memory Plugin |
| `ShortTermMemoryManager` | memory Plugin |
| `LongTermMemoryManager` | memory Plugin |
| `VectorStore` | memory Plugin |
| `ToolRegistry` | tools Plugin |
| `ToolEngine` | tools Plugin |
| `AgencyManager` | agency Plugin |
| `PlanningManager` | agency Plugin |
| `FlowExecutor` | agency Plugin |
| `LLMGateway` | agency Plugin |

不明なサービスは `manager.resolve_optional("Name")` で安全に取得。

### 6. プラグイン設定を使う（任意）

`config.yaml`:
```yaml
plugins:
  config:
    my_plugin:
      param1: value
```

```python
cfg = manager.get_plugin_config("my_plugin")
```

### 7. テストを追加する

- `tests/<plugin_name>/test_*.py`
- PluginManager の `discover_and_build_all()` + `start_all()` の結合テスト推奨
- 依存PluginはDIからFake注入

### 8. 無効化する（デバッグ時）

```yaml
plugins:
  disabled:
    - my_plugin
```

### 9. 検証してコミットする

```powershell
ruff check .
mypy .
pytest tests/ -q
git add .
git commit -m "feat: <plugin_name> プラグインを追加"
```

## Rules

- `__init__.py` に `MANIFEST` + `class XxxPlugin` + `plugin = XxxPlugin()` が必須
- `init(manager)` で DI resolve → create → wire → provide → hooks
- 依存は `MANIFEST.dependencies` に必ず宣言すること
- `manager.register_manifest(MANIFEST)` を `init()` の最初に呼ぶこと
- `PluginState` は PluginManager が管理する。プラグイン側で触らない
- `start()` / `stop()` は非ブロッキング。バックグラウンドは Plugin 内部でスレッド管理

## Plugin 標準実装契約

全 Plugin は以下の共通インターフェースを実装すること:

| メソッド | 必須 | 説明 |
|---|---|---|
| `init(manager)` | Yes | DI wiring + component creation + hook registration |
| `start(manager)` | No | バックグラウンドスレッド開始 |
| `stop(manager)` | No | リソースクリーンアップ |
| `get_state()` | No | デバッグスナップショット用の状態辞書を返す |
| `health()` | No | 健全性チェック。`(bool, str)` を返す |

## Plugin 内部ファイル分割規則

プラグイン内部のファイル分割・コンポーネント命名規則の詳細は `.agents/skills/iris-plugin-structure/SKILL.md` を参照。
