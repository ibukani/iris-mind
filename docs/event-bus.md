# EventBus インターフェース仕様書

## 概要

EventBus はコンポーネント間の疎結合通信を実現する publish/subscribe バス。
v0.3 では Protocol として抽象化され、in-memory / IPC / Replayable の3実装を持つ。

## インターフェース

### EventBusProtocol（抽象）

```python
class EventBusProtocol(Protocol):
    def publish(self, event: Event) -> None: ...
    def subscribe(self, event_type: str, handler: Callable) -> None: ...
    def unsubscribe(self, event_type: str, handler: Callable) -> None: ...
```

### EventBus（具象実装、v0.2 からの継続）

インメモリ同期型。単一プロセスモードで使用する。

```python
class EventBus:
    def publish(self, event: Event) -> None:
        """該当する全ハンドラを**登録順**に同期的に呼び出す。
        ハンドラ内例外はログ出力し、次のハンドラの実行を妨げない。"""
    def subscribe(self, event_type: str, handler: Callable) -> None: ...
    def unsubscribe(self, event_type: str, handler: Callable) -> None: ...
```

### ReplayableTransport（デバッグ用ラッパー）

```python
class ReplayableTransport:
    """PipeServer/PipeClient の前面に置き、送受信イベントを JSONL に記録する。
    記録されたイベント列は後で再生可能（ReplayTransport は未実装）。"""
```

動作は同期インメモリ。スレッドセーフ（`threading.Lock` で保護）。

## イベント種別

### Event（基底クラス）

| フィールド | 型 | 説明 |
|-----------|---|------|
| `timestamp` | `datetime \| None` | イベント生成時刻 |
| `source` | `str` | 発生源（`"user_input"`, `"proactive"`, `"system"`, `"timer"`, `"input:*"`, `"output:*"`） |
| `trace_id` | `str` | UUID4先頭12文字 — 全プロセス横断追跡ID（空文字列の場合は publish 時に自動生成） |

### UserInputEvent

| フィールド | 型 | 説明 |
|-----------|---|------|
| `content` | `str` | ユーザー入力テキスト |
| `metadata` | `dict \| None` | 追加メタデータ（チャネル、セッションID等） |

### ProactiveSpeechEvent

| フィールド | 型 | 説明 |
|-----------|---|------|
| `content` | `str` | 発話テキスト |
| `trigger_type` | `str` | トリガー種別（`"temporal"`, `"memory"`, `"context_shift"`） |
| `confidence` | `float` | 信頼度スコア（0.0〜1.0） |

### TimerTick

| フィールド | 型 | 説明 |
|-----------|---|------|
| `tick_count` | `int` | タイマー呼び出し回数（0始まり） |

### AgentStateChangeEvent

| フィールド | 型 | 説明 |
|-----------|---|------|
| `previous_state` | `str \| None` | 遷移前の状態名 |
| `new_state` | `str \| None` | 遷移後の状態名 |

### MemoryUpdateEvent

| フィールド | 型 | 説明 |
|-----------|---|------|
| `entry_type` | `str` | 記憶種別 |
| `content` | `str` | 記憶内容 |

### AgentStreamEvent

| フィールド | 型 | 説明 |
|-----------|---|------|
| `delta` | `str` | LLM ストリーミングトークン |
| `done` | `bool` | ストリーム完了フラグ |

### AgentResponseEvent

| フィールド | 型 | 説明 |
|-----------|---|------|
| `content` | `str` | LLM応答テキスト |
| `model` | `str` | 応答に使用されたモデル名 |

### AgentAnomalyEvent

| フィールド | 型 | 説明 |
|-----------|---|------|
| `anomaly_type` | `str` | 異常種別（`"frequency_exceeded"`, `"confirmation_mode"`, `"high_ignore_rate"`） |
| `severity` | `str` | 深刻度（`"warning"`, `"info"`） |
| `detail` | `str` | 詳細説明 |

## 動作仕様（EventBus 具象実装）

- `publish()`: 該当イベントタイプの全ハンドラを**登録順**に同期的に呼び出す
- ハンドラ内例外はログ出力し、次のハンドラの実行を妨げない
- `subscribe()`: 同じハンドラの重複登録は許可（解除時は初回一致のみ削除）
- `unsubscribe()`: 該当ハンドラが見つからなければ何もしない
- `publish()`: `trace_id` が空文字列の場合、自動で `new_trace_id()` を生成してセットする
- スレッドセーフ: `threading.Lock` で購読者リストを保護

## プロセス間通信（IPC）

マルチプロセスモードでは `InputBridge` / `OutputBridge` を使用する。

### Kernel 側

```python
class OutputBridge:
    """EventBus のイベントを購読し、Named Pipe を通じて Output Process に中継する。"""
    def __init__(self, event_bus: EventBusProtocol, pipe_address: str):
        self._subscribe()
    def start(self):
        """PipeServer を起動し、accept ループを開始する。"""
    def stop(self):
        """全コネクションを切断し、サブスクリプションを解除する。"""
```

### Output Process 側

`PipeClient.recv()` でイベントを受信し、`renderer.py` で表示する。
ループは `output_main.py` で管理される。

## 配信例

```
[単一プロセスモード]
UserInputEvent → AgentKernel._on_user_input()
                 → ConversationService._on_user_input()
                   → AgentResponseEvent を publish
                     ├─ AgentKernel: PROCESSING→IDLE
                     ├─ CLIAdapter: 表示
                     └─ MemoryManager: 記録

[マルチプロセスモード]
Input Process → Pipe → Kernel Process → Pipe → Output Process
```

## 注意事項

- イベントクラスは全て `Event` を基底クラスとし、`dataclass` で定義すること
- `source` フィールドはイベントの発生源デバッグ用。省略不可
- `trace_id` は Input Process で生成し、Kernel → Output まで伝搬すること
- IPC 使用時は JSON でシリアライズされる（`ipc.py:_serialize()` / `_deserialize()`）
- デバッグ用の `ReplayableTransport` は `to_dict()` の出力を JSONL に記録する
