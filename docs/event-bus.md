# EventBus インターフェース仕様書

## 概要

EventBus はコンポーネント間の疎結合通信を実現する publish/subscribe バス。
v0.3 では Protocol として抽象化され、in-memory / Replayable の2実装を持つ。IPC 関連は削除され、EventBus は Kernel 内部のイベントのみを扱う。

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
    """EventBus の前面に置き、送受信イベントを JSONL に記録する。
    記録されたイベント列は後で再生可能（ReplayTransport は未実装）。"""
```

動作は同期インメモリ。スレッドセーフ（`threading.Lock` で保護）。

## イベント種別

### Event（基底クラス）

| フィールド | 型 | 説明 |
|-----------|---|------|
| `timestamp` | `datetime \| None` | イベント生成時刻 |
| `source` | `str` | 発生源（`"system"`, `"timer"`, `"proactive"`, `"kernel"`） |
| `trace_id` | `str` | UUID4先頭12文字 — 全プロセス横断追跡ID（空文字列の場合は publish 時に自動生成） |

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

## 配信例

```
[内部イベントフロー例]
TimerTick → ProactiveEngine._on_timer_tick()
            → 必要に応じて会話を開始

AgentStateChangeEvent → AgentKernel: 状態遷移を検知
                      └─ MemoryManager: 状態変化を記録

MemoryUpdateEvent → MemoryManager: 記憶の永続化トリガー

AgentAnomalyEvent → AgentKernel: 異常検知時のアクション
```

## 注意事項

- イベントクラスは全て `Event` を基底クラスとし、`dataclass` で定義すること
- `source` フィールドはイベントの発生源デバッグ用。省略不可
- `trace_id` は EventBus が空文字列の場合に自動生成する
- デバッグ用の `ReplayableTransport` は `to_dict()` の出力を JSONL に記録する
