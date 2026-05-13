# EventBus インターフェース仕様書

## 概要

インメモリ同期イベントバス。コンポーネント間の疎結合通信を実現する。

## インターフェース

```python
class EventBus:
    def publish(self, event: Event) -> None: ...
    def subscribe(self, event_type: str, handler: Callable) -> None: ...
    def unsubscribe(self, event_type: str, handler: Callable) -> None: ...
```

## イベント種別

### Event（基底クラス）

| フィールド | 型 | 説明 |
|-----------|---|------|
| `timestamp` | `datetime` | イベント生成時刻 |
| `source` | `str` | 発生源（`"user_input"`, `"proactive"`, `"system"`, `"timer"`） |

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

### MemoryUpdateEvent

| フィールド | 型 | 説明 |
|-----------|---|------|
| `entry_type` | `str` | `"episodic"` または `"semantic"` |
| `content` | `str` | 記憶の内容 |

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

## 動作仕様

- `publish()`: 該当イベントタイプの全ハンドラを**登録順**に同期的に呼び出す
- ハンドラ内例外はログ出力し、次のハンドラの実行を妨げない
- `subscribe()`: 同じハンドラの重複登録は許可（解除時に全件削除される）
- `unsubscribe()`: 該当ハンドラが見つからなければ何もしない

## 配信例

```
TimerTick → ProactiveEngine.check_trigger()
             ├─ (発話不要) → 何もpublishしない
             └─ (発話必要) → ProactiveSpeechEvent を publish
                              ├─ CliAdapter: 表示
                              ├─ MemoryManager: 記録
                              └─ Reflexion: 評価スケジューリング

UserInputEvent → AgentKernel._on_user_input()（IDLE→PROCESSING）
                 → ConversationService._on_user_input()
                 → AgentResponseEvent を publish
                      ├─ CliAdapter: 表示
                      ├─ AgentKernel: PROCESSING→IDLE
                      └─ MemoryManager: 記録

AgentAnomalyEvent → AgentKernel（Tier3異常検知時）
                    → CliAdapter: 警告パネル表示
```

## 注意事項

- 現状はインメモリ同期型のため、プロセスをまたいだ配信は不可
- 将来の分散対応に備え、イベントのシリアライズ形式はJSON互換にすること
- イベントクラスは全て `Event` を基底クラスとし、`dataclass` で定義すること
- `source` フィールドはイベントの発生源デバッグ用。省略不可
