---
name: iris-plugin-create
description: |
  Use ONLY when creating a brand-new top-level Iris Plugin class under iris/<plugin_name>/.
  Do NOT use: modifying existing plugins, adding hooks, adding @tool capabilities,
  adding LLM providers, adding store backends, or adding sub-plugins.
license: MIT
metadata:
  audience: developers
  workflow: iris-extension
---

## Purpose

Iris に新しいトップレベルPluginを追加するときに読む。
@tool capability は `capability-pattern`、LLM provider / store backend は `iris-plugin-provider`、Hook は `iris-plugin-hook` を読む。
すべてのトップレベルPluginは `PluginProtocol` に準拠する。
詳細な `PluginProtocol` / `PluginManifest` / lifecycle 定義は `iris/kernel/plugin/` の実装を一次情報にする。以下は現在の標準パターン。

## Plugin カテゴリ

| カテゴリ | Phase | 説明 | 例 |
|---|---|---|---|
| `CORE` | 10 | 必須インフラ層 | io, llm, tools |
| `LAYER` | 15/20/30 | データ層・認知層・高度認知 | account, room, memory, limbic, agency |
| `FEATURE` | 40 | 機能拡張 | 任意機能 |
| `PROVIDER` | 親に従う | 実装差し替え | 外部プロバイダPlugin |
| `TOOL` | 10/40 | ツール基盤・ツール拡張 | tools |

`COGNITIVE` は `PluginPhase` であり `PluginCategory` ではない。

## Steps

### 1. ディレクトリを作成する

```
iris/<plugin_name>/
├── __init__.py     # MANIFEST + プラグインクラス + plugin インスタンス
├── manager.py      # 任意: 中心サービス / オーケストレータ
├── hooks.py        # 任意: register_hooks(manager)
├── handler.py      # 任意: EventBus購読 (_XxxEventHandler)
├── events.py       # 任意: プラグイン固有イベント型
├── models.py       # 任意: プラグイン固有の型
└── tools/          # 任意: @tool 定義 (TOOLカテゴリの場合)
    └── __init__.py
```

### 2. `__init__.py` を作成する

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from iris.event.event_bus import EventBus
from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol

from .manager import MyService

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager

MANIFEST = PluginManifest(
    name="my_plugin",
    version="0.1.0",
    category=PluginCategory.FEATURE,
    phase=PluginPhase.FEATURE,
    dependencies={"EventBus", "LLMBridge"},  # プラグイン名 / provides名 / 組み込みサービス名
    provides=["MyService"],
    description="プラグインの説明",
)


class MyPlugin(PluginProtocol):
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        """DI登録 + コンポーネント生成 + 配線 + Hook購読"""
        manager.register_manifest(MANIFEST)

        event_bus = manager.resolve(EventBus)
        instance = MyService(event_bus=event_bus)
        manager.provide(MyService, instance)

        from .hooks import register_hooks
        register_hooks(manager)

    def start(self, manager: PluginManager) -> None:
        """バックグラウンド処理開始（任意）"""
        pass

    def stop(self, manager: PluginManager) -> None:
        """クリーンアップ（任意）"""
        pass


plugin: PluginProtocol = MyPlugin()
```

### 3. `hooks.py` を作成する（任意）

```python
def register_hooks(manager) -> None:
    hooks = manager.hook_registry

    def _my_hook(data):
        return data

    hooks.register("llm.before_chat", _my_hook, priority=500)
```

利用可能な HookPoint 一覧は `.agents/skills/iris-plugin-hook/SKILL.md` を参照。

### 4. `handler.py` を作成する（EventBus購読がある場合は必須）

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from iris.event.event_types import MessageEvent

if TYPE_CHECKING:
    from .manager import MyService


class _MyEventHandler:
    def __init__(self, event_bus: Any, service: MyService) -> None:
        self._service = service
        event_bus.subscribe(MessageEvent, self._on_message_event)

    def _on_message_event(self, event: MessageEvent) -> None:
        self._service.handle(event)
```

`__init__.py` の `init()` 内で生成して配線する。EventBus購読を manager や managerクラスに置かない。

### 5. 依存を確認する

`MANIFEST.dependencies` は依存するプラグイン名、`provides` 名、または組み込みサービス名を文字列で宣言する。
DIの取得・登録は型キーで行う。

PluginManager が提供する標準サービス:

| 依存文字列 | DI型 | 提供元 |
|---|---|---|
| `EventBus` | `EventBus` | PluginManager（インフラ） |
| `HookRegistry` | `HookRegistry` | PluginManager（インフラ） |
| `Config` | `Config` | PluginManager（インフラ） |
| `PluginManager` | `PluginManager` | PluginManager（自己） |
| `IOManager` | `IOManager` | io Plugin |
| `SessionManager` | `SessionManager` | io Plugin |
| `GrpcListener` | `GrpcListener` | io Plugin |
| `LLMBridge` | `LLMBridge` | llm Plugin |
| `DebugCapture` | `DebugCapture` | llm Plugin |
| `CapabilityChecker` | `CapabilityChecker` | llm Plugin |
| `MemoryManager` | `MemoryManager` | memory Plugin |
| `SensoryMemoryManager` | `SensoryMemoryManager` | memory Plugin |
| `ShortTermMemoryManager` | `ShortTermMemoryManager` | memory Plugin |
| `LongTermMemoryManager` | `LongTermMemoryManager` | memory Plugin |
| `VectorStore` | `VectorStore` | memory Plugin |
| `ToolRegistry` | `ToolRegistry` | tools Plugin |
| `ToolEngine` | `ToolEngine` | tools/agency Plugin |
| `AgencyManager` | `AgencyManager` | agency Plugin |
| `PlanningManager` | `PlanningManager` | agency Plugin |
| `FlowExecutor` | `FlowExecutor` | agency Plugin |
| `LLMGateway` | `LLMGateway` | agency Plugin |

任意依存は `manager.resolve_optional(ServiceType)` で安全に取得。

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

### 9. 検証する

検証のみ:

```bash
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

修正を許可されている場合:

```bash
uv run ruff check --fix .
uv run ruff format .
```

### 10. コミットする

ユーザーが明示的に依頼した場合のみ行う。

```bash
git add .
git commit -m "feat: <plugin_name> プラグインを追加"
```

## Rules

- `__init__.py` に `MANIFEST` + `class XxxPlugin` + `plugin = XxxPlugin()` が必須
- `init(manager)` で DI resolve → create → wire → provide → hooks
- 依存は `MANIFEST.dependencies` に必ず宣言すること（未解決依存は起動時に `DependencyError` が発生）
- `manager.register_manifest(MANIFEST)` を `init()` の最初に呼ぶこと
- PluginState は PluginManager が管理する。プラグイン側で触らない
- `start()` / `stop()` は非ブロッキング。バックグラウンドは Plugin 内部でスレッド管理
- EventBus subscribe は型安全版を使用すること（`bus.subscribe(TimerTick, handler)`）
- ホットリロード: `manager.reload_plugin("plugin_name")` で実行中の再読み込みが可能
- capability / tool 追加だけならこのSkillを使わず `capability-pattern` を読む
- LLM provider / store backend / sub-plugin 追加だけならこのSkillを使わず `iris-plugin-provider` を読む

## Plugin 標準実装契約

全 Plugin は以下の共通インターフェースを実装すること:

| メソッド | 必須 | 説明 |
|---|---|---|
| `init(manager)` | Yes | DI wiring + component creation + hook registration |
| `start(manager)` | No | バックグラウンドスレッド開始 |
| `stop(manager)` | No | リソースクリーンアップ |
| `on_config_loaded(manager)` | No | 全プラグイン init 後に呼ばれる。設定の最終確認に使用 |
| `on_all_ready(manager)` | No | 全プラグイン start 後に呼ばれる。遅延初期化に使用 |
| `on_pre_shutdown(manager)` | No | シャットダウン前に呼ばれる。リソース解放の前に実行 |
| `get_state()` | No | デバッグスナップショット用の状態辞書を返す |
| `health()` | No | 健全性チェック。`(bool, str)` を返す |

### Lifecycle フックの使い分け

```
discover_and_build_all():
  init_all() → notify_config_loaded() → freeze

start_all():
  start_all() → mark_all_ready() → notify_all_ready()

stop_all():
  notify_pre_shutdown() → stop_all()
```

- `on_config_loaded`: DI が確定した直後。設定値の最終検証に使用
- `on_all_ready`: 全プラグインが起動した後。他プラグインへの依存が全て揃った状態
- `on_pre_shutdown`: stop の前。非同期処理の完了待ち等に使用

## Plugin 内部ファイル分割規則

新規作成時に遵守すべきstructure規則を以下にまとめる。詳細は `.agents/skills/iris-plugin-structure/SKILL.md` を参照。

### ファイル名規約

- `snake_case.py`。略語禁止（`di.py` → `service_container.py`）
- 単数形優先。コンテナのみ複数形可（`protocols.py`, `stores.py`）
- 数字接尾辞禁止（`handler2.py` ではなく責務名で分割）

### クラス名規約

- `PascalCase`。ファイル名とプレフィックスを一致させる
  - `manager.py` → `XxxManager`
  - `handler.py` → `_XxxEventHandler`（`_` プレフィックス必須）
- Protocol は `XxxProtocol` 命名推奨

### 関数名規約

- モジュールレベル: `動詞_目的語`（`build_agency`, `route_after_llm`, `render_short_term_context`）
- ハンドラ（EventBus購読）: **`_on_xxx_event`**（`_on_message_event`, `_on_tick`）
- Hook ハンドラ: **`_xxx_hook`**（`_my_hook`）
- プライベート: `_prefix`

### handler.py 分離ルール

- EventBus subscribe は manager で直接行わず、必ず `handler.py` に分離
- `__init__.py` の `init()` で wiring する
- handler が manager のメソッドを呼び戻す場合は `Protocol` を介して疎結合にする

### 分割トリガー（新規作成時の判断基準）

| 条件 | 抽出先 |
|---|---|
| `__init__.py` の `init()` 本体 > 50行 | `builder.py` |
| EventBus subscribe が1つでもある | `handler.py`（必須分離） |
| Protocol クラスが3以上 | `protocols.py` |
| static method が2以上 | `utils.py` |
| コンポーネント生成が複雑（> 10行） | `builder.py` |

### インポート規約

- **同一プラグイン内**: 相対インポート推奨（`from .manager import XxxManager`）
- **他プラグイン**: 絶対インポート（`from iris.memory.manager import MemoryManager`）
- 循環参照の回避: 型ヒントのみの参照は `if TYPE_CHECKING:` ブロック内でインポート

### その他の重要ルール

- PluginManager をロジッククラスのメンバ変数に保持させない。コンストラクタで具象依存を注入する
- 1ファイル200行を目安に、超えたら責務分割を検討
- 分割トリガーに達する前の過剰分割は禁止。必要になるまで単一ファイルで良い。EventBus subscribe の分離のみ例外
- `__init__.py` は公開APIのみ再エクスポート。内部モジュールへの直接アクセスは非推奨
- `models.py` はデータ保持用ピュアクラスのみ。シリアライズ/変換は `formatter.py` / `renderer.py` で行う
