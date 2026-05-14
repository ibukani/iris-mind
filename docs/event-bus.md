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

### ReplayableEventBus（デバッグ用デコレータ）

```python
class ReplayableEventBus:
    """実 EventBus の前面に置き、全イベントを JSONL に記録するデコレータ。
    記録されたイベント列は後で再生可能。"""
```

動作は同期インメモリ。スレッドセーフ（`threading.Lock` で保護）。

## イベント種別

### Event（基底クラス）

| フィールド | 型 | 説明 |
|-----------|---|------|
| `timestamp` | `datetime` | イベント生成時刻 |
| `source` | `str` | 発生源（`"user_input"`, `"proactive"`, `"system"`, `"timer"`, `"input:*"`, `"output:*"`） |
| `trace_id` | `str` | UUID4 — 全プロセス横断追跡ID (v0.3 で追加) |

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
| `previous_state` | `str` | 遷移前の状態名 |
| `new_state` | `str` | 遷移後の状態名 |

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
- `subscribe()`: 同じハンドラの重複登録は許可（解除時に全件削除される）
- `unsubscribe()`: 該当ハンドラが見つからなければ何もしない
- スレッドセーフ: `threading.Lock` で購読者リストを保護

## プロセス間通信（IPC）

マルチプロセスモードでは `PipeBridge` を使用する。

### Kernel 側

```python
class OutputBridge:
    """EventBus のイベントを購読し、Named Pipe を通じて Output Process に中継する。"""
    def __init__(self, event_bus: EventBusProtocol, pipe_client: PipeClient):
        event_bus.subscribe("AgentStreamEvent", self._on_stream_token)
        event_bus.subscribe("AgentResponseEvent", self._on_response)
        event_bus.subscribe("ProactiveSpeechEvent", self._on_proactive)
        event_bus.subscribe("AgentAnomalyEvent", self._on_anomaly)
```

### Output Process 側

```python
class PipeClient:
    """Named Pipe からイベントを受信し、対応するハンドラに配送する。"""
    def recv_loop(self): ...
```

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
- IPC 使用時は pickle でシリアライズされるため、イベントクラスは pickle 可能であること
- デバッグ用の `ReplayableEventBus` は JSONL に記録するため、`to_dict()` / `from_dict()` を持つこと
