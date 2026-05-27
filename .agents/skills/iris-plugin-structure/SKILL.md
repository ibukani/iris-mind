---
name: iris-plugin-structure
description: Iris プラグイン内部のファイル分割・コンポーネント命名規則
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: iris-extension
---

## Purpose

既存プラグインの内部ファイルを整理・分割するとき、または新規プラグインのコンポーネント構成を決めるときに読む。
`iris-plugin-create` が「新規作成」手順を提供するのに対し、本スキルは「内部構造の設計規約と命名規則」を定義する。

## 基本原則

- **1ファイル = 1責務**。単一責務を超えたら分割する
- **ファイル名から責務が推測できる**こと
- **クラス名とファイル名を対応させる**: `manager.py` → `XxxManager`、`protocols.py` → `XxxProtocol`
- **内部実装は `_leading_underscore`** で外部からの直接使用を防ぐ
- **依存性逆転の原則 (DIP)**: 他プラグインとの連携は具象クラスではなく `Protocol` を介して行う
- **依存性注入 (DI) の徹底**: `PluginManager` をロジッククラス内に保持して動的に解決する（サービスロケーターパターン）のを禁止し、すべてコンストラクタで明示的に注入する
- **純粋ロジックとI/Oの分離**: スコアラーやエクストラクター等は純粋なデータ処理に徹し、ファイルI/OやEventBusパブリッシュなどの副作用を持たせない

## 標準ディレクトリ構成

```
iris/<plugin_name>/
├── __init__.py           # MANIFEST + Plugin クラス + plugin インスタンス
├── builder.py            # コンポーネント組み立て（init() が複雑な場合）
├── manager.py            # コアオーケストレータ
├── handler.py            # EventBus イベントハンドラ
├── dispatcher.py         # store/retrieve/search のルーティング
├── router.py             # 条件分岐ルーティング
├── protocol.py           # 1件の Protocol 定義
├── protocols.py          # 複数の Protocol 定義
├── models.py             # dataclass / TypedDict / Pydantic
├── base.py               # 抽象基底クラス
├── hooks.py              # HookPoint 登録
├── events.py             # プラグイン固有イベント型
├── utils.py              # ユーティリティ関数
├── scorer.py             # スコアリング/評価
├── extractor.py          # エンティティ抽出
├── renderer.py           # フォーマット/レンダリング
├── formatter.py          # 出力整形
├── param_builder.py      # パラメータ構築
├── config.py             # 設定読み込み
└── tools/                # @tool 定義（TOOLカテゴリ向け）
    └── __init__.py
```

## ファイル別命名規則

### 責務: オーケストレーション

| ファイル | 含めるもの | クラス名パターン | 実装例 |
|---|---|---|---|
| `manager.py` | 中心オーケストレータ | `XxxManager` | `MemoryManager`, `LimbicManager`, `AgencyManager` |
| `handler.py` | EventBus イベント購読 | `_XxxEventHandler` (private) | `_MemoryEventHandler` |
| `dispatcher.py` | 操作の振り分け | `build_xxx_handlers()` + `_xxx_yyy()` | `build_store_handlers()` + `_store_sensory()` |
| `router.py` | 条件分岐 | `route_xxx_yyy()` | `route_after_llm(state) -> str` |
| `builder.py` | コンポーネント組立 | `build_xxx(manager)` | `build_agency(manager) -> dict` |

### 責務: データ構造

| ファイル | 含めるもの | クラス名パターン | 実装例 |
|---|---|---|---|
| `models.py` | データ型定義 | `XxxData`, `XxxState` | `TurnData`, `SearchResult`, `ExecutionState` |
| `protocol.py` | 単一 Protocol | `XxxProtocol` | `MemoryManagerProtocol` |
| `protocols.py` | 複数 Protocol | `XxxProtocol` | `EpisodicStoreProtocol`, `SemanticStoreProtocol` |
| `base.py` | 抽象基底 | `_XxxBase` (private) | `_JsonlStore` |

### 責務: 単一処理

| ファイル | 含めるもの | クラス名パターン | 実装例 |
|---|---|---|---|
| `scorer.py` | スコアリング | `XxxScorer` (Protocol) + `DefaultXxxScorer` | `ImportanceScorer` + `DefaultImportanceScorer` |
| `extractor.py` | 抽出/解析 | `XxxExtractor` (Protocol) + `ConcreteExtractor` | `EntityExtractor` + `RegexEntityExtractor` |
| `renderer.py` | レンダリング | `render_xxx_context(...)` | `render_short_term_context(turns, ...) -> str` |
| `formatter.py` | 出力整形 | `XxxFormatter` | `CaptureFormatter` |
| `param_builder.py` | パラメータ構築 | `build_xxx_yyy()` | — |
| `utils.py` | ユーティリティ | `xxx_yyy()` (関数) | `build_time_label() -> str` |
| `config.py` | 設定読み込み | `XxxConfig` | — |

### 責務: フックとイベント

| ファイル | 含めるもの | 関数名パターン |
|---|---|---|
| `hooks.py` | HookPoint 登録 | `register_hooks(manager)` |
| `events.py` | イベント型定義 | `XxxEvent(DataClass)` |

## 分割トリガー

| 条件 | 抽出先 |
|---|---|
| `__init__.py` の `init()` 本体 > 50行 | `builder.py` に分割 |
| ファイル > 200行 かつ 責務が2以上 | 責務ごとにファイル分割 |
| EventBus subscribe が3以上 かつ handlerがmanager内部状態に依存しない | `handler.py` に抽出 |
| Protocol クラスが3以上 | `protocols.py` に集約（複数形） |
| 基底クラスがある | `base.py` に抽出 |
| モジュールレベル関数のみのファイルがある | 関数の責務を確認し、責務が単一なら維持も可（`utils.py`, `router.py`） |
| static method が2以上 | `utils.py` に抽出 |
| コンポーネント生成が複雑（> 10行） | `builder.py` に抽出 |

## 命名規則詳細

### ファイル名
- `snake_case.py`。略語禁止（`di.py` → `service_container.py`）
- 単数形優先。ただし複数エンティティのコンテナは複数形可（`protocols.py`, `stores.py`）
- 数字接尾辞禁止（`handler2.py` ではなく責務名で分割）

### クラス名
- `PascalCase`。ファイル名とプレフィックスを合わせる
  - `manager.py` → クラス名は `XxxManager`
  - `protocols.py` → クラス名は `XxxProtocol`
- 内部専用クラスは `_` プレフィックス（`_MemoryEventHandler`, `_JsonlStore`）
- Protocol クラスは `XxxProtocol` の命名を推奨（`typing.Protocol` のサブクラスであることが明示的）

### 関数名
- `snake_case`。モジュールレベル関数は `動詞_目的語` パターン
  - `build_agency`, `route_after_llm`, `render_short_term_context`
- プライベート関数は `_prefix`
- ハンドラは `_on_xxx_event`（イベント購読用）、`_xxx_hook`（Hook用）

### 定数
- `UPPER_SNAKE_CASE`
- モジュールレベル定数はファイル先頭に集約

## プライベート可視性ルール

| 可視性 | 命名 | 使用範囲 |
|---|---|---|
| 公開API | `XxxManager`, `build_xxx()` | 他Pluginからの利用を意図 |
| 内部実装 | `_XxxHandler`, `_xxx_helper()` | 同一Plugin内のみ |
| 同一ファイルのみ | 関数内関数 / ネストクラス | 関数スコープ内 |

## パッケージ内インポート規約

- **同一プラグイン内**: 相対インポート推奨（`from .manager import XxxManager`）
- **他プラグイン**: 絶対インポート（`from iris.memory.manager import MemoryManager`）
- `__init__.py` は公開APIのみ再エクスポート。内部モジュールへの直接アクセスは非推奨
- **循環参照の回避**: 型ヒントのみで参照するクラスは `if TYPE_CHECKING:` ブロック内でインポートし、ランタイムのインポートループを防ぐ

## サブプラグイン・プロバイダ構造

```
iris/llm/providers/           # LLM プロバイダ
├── __init__.py               # 集約 register 関数
├── ollama.py                 # register(bridge) 関数
├── openrouter.py
└── google.py

iris/tools/builtins/          # 組み込みツール
├── __init__.py
└── <tool_name>/
    └── server.py             # register(registry) 関数
```

- サブプラグインは `register(parent)` 単一関数をエクスポート
- ファイル名はプロバイダ/ツール名をそのまま使う（`ollama.py`, `git.py`）

## 実装パターン集

### Builder（組立関数）と `__init__.py` の連携

```python
# iris/<plugin>/__init__.py
from __future__ import annotations
from iris.kernel.plugin.protocol import PluginProtocol, PluginManager
from .builder import build_components

class XxxPlugin(PluginProtocol):
    def init(self, manager: PluginManager) -> None:
        # 複雑なコンポーネント組み立てを builder に委譲
        self._components = build_components(manager)

# iris/<plugin>/builder.py
from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from iris.kernel.plugin.protocol import PluginManager

def build_components(manager: PluginManager) -> dict[str, Any]:
    dependency = manager.resolve("SomeService")
    component = XxxManager(dependency)
    manager.provide("XxxManager", component)
    return {"manager": component}
```

### サブプラグイン自動発見と登録

```python
# iris/<plugin>/__init__.py
from __future__ import annotations
from iris.kernel.plugin.loader import discover_sub_plugins
from iris.kernel.plugin.protocol import PluginProtocol, PluginManager

class ParentPlugin(PluginProtocol):
    def init(self, manager: PluginManager) -> None:
        # サブプラグイン (プロバイダなど) を自動検知して登録
        sub_plugins = discover_sub_plugins(
            package_path="iris/<plugin>/providers",
            package_name="iris.<plugin>.providers"
        )
        for _, register_fn in sub_plugins:
            register_fn(self)  # 親プラグインに自身を登録させる
```

### Handler（イベント購読）

```python
# iris/<plugin>/handler.py
from __future__ import annotations
from typing import Any

class _XxxEventHandler:
    def __init__(self, event_bus: Any, dependency: Any) -> None:
        event_bus.subscribe("SomeEvent", self._on_event)

    def _on_event(self, event: SomeEvent) -> None:
        ...
```

### Protocol + 実装

```python
# iris/<plugin>/scorer.py
from __future__ import annotations
from typing import Protocol

class XxxScorer(Protocol):
    def score(self, data: InputType) -> int: ...

class DefaultXxxScorer:
    def score(self, data: InputType) -> int:
        return 0
```

### Dispatcher（振り分け）

```python
# iris/<plugin>/dispatcher.py
from __future__ import annotations
from collections.abc import Callable
from typing import Any

def build_dispatch_handlers(...) -> dict[str, Callable[..., Any]]:
    return {
        "store": _store_impl,
        "search": _search_impl,
    }

def _store_impl(data: Any) -> None: ...
def _search_impl(query: Any) -> list[Any]: ...
```

## 既存Pluginの構造例

| Plugin | mainファイル | サブファイル |
|---|---|---|
| `memory/` | `manager.py` | `handler.py`, `dispatcher.py`, `protocol.py` + `short_term/{manager,models,scorer,extractor,renderer}.py` + `long_term/{manager,stores,protocols,base,vector_store,goal_store}.py` + `sensory/manager.py` + `hippocampal/` |
| `agency/` | `manager.py` | `builder.py`, `bus.py`, `task_level.py` + `planning/{manager,scorer,context_hint_builder,utils}.py` + `execution/{orchestrator,router,executor,models,engine}.py` + `execution/llm/{gateway,prompt_builder}.py` + `execution/nodes/{base,general_chat,general_task,setup,tool_run,finalize,post_process}.py` + `regulation/{consolidator,feedback,output_tracker,talk_control}.py` |
| `limbic/` | `manager.py` | `models.py`, `amygdala.py`, `acc.py`, `emotional_memory.py`, `big_five.py` |
| `llm/` | - | `llm_bridge.py`, `provider.py`, `ollama_provider.py`, `openrouter_provider.py`, `capability_checker.py`, `tokenizer_manager.py`, `context_window.py`, `prompt_builder.py`, `interrupt_token.py` |

## Rules

- ファイル名は必ず `snake_case.py`。略語禁止。単数形優先
- クラス名は `PascalCase` でファイル名とのプレフィックス一致を意識
- 内部クラスは `_` プレフィックス。外部から `import` させない
- 分割トリガーに達する前の過剰分割は禁止。必要になるまで単一ファイルで良い
- `__init__.py` の `init()` が 50行を超えたら `builder.py` に切り出す
- 1ファイル200行を目安に、超えたら責務分割を検討
- `PluginManager` インスタンスをロジッククラス（`XxxManager` 等）のメンバ変数に保持させない（コンストラクタで具象依存を注入する）
- `models.py` にはデータ保持用のピュアなクラスのみを定義し、APIやVDB用のシリアライズ/デシリアライズ等の外部表現変換は `formatter.py` や `renderer.py` 等で行う
