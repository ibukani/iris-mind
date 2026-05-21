# Skill: iris-debug

## 概要

Iris Kernel のデバッグ基盤。1種類のイベント（DebugSnapshotEvent）+ 命名規約（get_state）で全状態をカバー。

## アーキテクチャ

```
  [LimbicManager]       [HippocampalManager]
       |                        |
       | DebugSnapshotEvent     | DebugSnapshotEvent
       v                        v
  +-----------------------------------------+
  |           EventBus                       |
  |  publish() -> tracer.on_event()         |
  +-----------------------------------------+
       |
       v
  +-----------------------------------------+
  |  EventTracer (RingBuffer 500)           |
  |   - category index (limbic.emotion,     |
  |     personality.big_five)               |
  +-----------------------------------------+

  SystemDiagnostics:
  +-----------------------------------------+
  |  get_state() auto-discovery             |
  |   - kernel/manager.py                   |
  |   - io/manager.py                       |
  |   - memory/manager.py                   |
  |   - limbic/manager.py                   |
  |   - agency/manager.py                   |
  |   - planning/manager.py                 |
  |   - execution/manager.py                |
  |   - big_five.py                         |
  |  query(path)                            |
  |  health()                               |
  |  generate_report()                      |
  +-----------------------------------------+

  Client Access Paths:
  +-------------------+                     +--------------------+
  | Human (console)   |---- /state etc --->| CommandHandler     |
  +-------------------+                     | _debug()           |
                                           | _state_cmd()       |
  +-------------------+                    | _events_cmd()      |
  | AI Agent (gRPC)   |--- /cmd ---------->| _health_cmd()      |
  | (Codex/Claude)    |                    | _report_cmd()      |
  +-------------------+                    +--------------------+
       ^
       | python -m debug_tools.cli state --json
       |
  +-------------------+
  | debug_tools/cli   |
  | .py               |
  +-------------------+
```

## 管理コンソールコマンド

| コマンド | エイリアス | 説明 |
|----------|-----------|------|
| `/debug help` | - | デバッグサブコマンド一覧 |
| `/debug state [<path>] [--history] [--json]` | `/state` | システム状態を表示 |
| `/debug events [n] [--type=TYPE]` | `/events` | 直近n件のイベント |
| `/debug health` | `/health` | 全コンポーネント健康診断 |
| `/debug report` | `/report` | Markdownデバッグレポート生成 |
| `/debug [on|off|list|last|show|dump]` | - | LLM入出力キャプチャ制御 |

### 使用例

```
> /state
kernel:
  global_state: IDLE
  layer_states: {limbic: IDLE, memory: IDLE, ...}

> /state limbic.emotion
valence: 0.12
arousal: -0.05
dominance: 0.30

> /state limbic --history
[2026-05-21T18:30:00] message -> valence=0.12 arousal=-0.05 dominance=0.30
[2026-05-21T18:30:05] decay -> valence=0.08 arousal=-0.03 dominance=0.28

> /events 3
[2026-05-21T18:30:00] DebugSnapshotEvent <limbic> [limbic.emotion] tid=abc123
[2026-05-21T18:30:05] TimerTick <kernel> tid=abc124
[2026-05-21T18:30:05] DebugSnapshotEvent <limbic> [limbic.emotion] tid=abc125

> /health
  o kernel: not loaded
  v io: OK
  v memory: OK (no health check)
  v limbic: OK (no health check)
  v agency: OK (no health check)
  v eventbus: OK (published=42, errors=0)

> /report
# Iris Debug Report
**Generated**: 2026-05-21 18:30:00
...
```

## パス一覧（状態ツリー）

- `kernel` -> KernelManager.get_state() -> global_state, layer_states
- `io` -> IOManager.get_state() -> listening, sessions count
- `memory` -> MemoryManager.get_state() -> episodic count, semantic count
- `limbic` -> LimbicManager.get_state() -> emotion (PAD), mood
- `limbic.emotion` -> valence, arousal, dominance (数値)
- `limbic.mood` -> 文字列 (例: "slightly positive")
- `agency` -> AgencyManager.get_state() -> planning, execution
- `agency.planning` -> suppressed, reason, go_signal
- `agency.execution` -> is_reflecting, msg_count, idle_seconds
- `eventbus` -> subscribers, total_published, errors

## カテゴリ（DebugSnapshotEvent history 用）

- `limbic.emotion` -> 感情変化（trigger: message / decay / monitor / stimulus）
- `personality.big_five` -> BigFive変化（trigger: reflection）

## gRPC CLI（外部AIエージェント用）

```bash
# 環境変数
export IRIS_HOST=127.0.0.1
export IRIS_PORT=9876
export IRIS_ACCESS_TOKEN=...

# Iris未起動時に自動起動
python -m debug_tools.cli state --spawn
python -m debug_tools.cli state limbic.emotion --json --spawn

# 状態取得
python -m debug_tools.cli state
python -m debug_tools.cli state limbic.emotion --json
python -m debug_tools.cli state limbic --history

# イベントトレース
python -m debug_tools.cli events
python -m debug_tools.cli events 20 --type=DebugSnapshotEvent

# 健康診断・レポート
python -m debug_tools.cli health
python -m debug_tools.cli report
```

## 新しい値を追加する手順

1. 該当クラスに `get_state()` メソッドを追加（dictを返す）
2. 状態変化時に `DebugSnapshotEvent(category="<category>", data=<state dict>)` を publish
3. コマンド変更は不要 -- path ベースで自動露出

例:
```python
class FooManager:
    def get_state(self) -> dict:
        return {"bar": self._bar, "baz": self._baz}

    def _on_change(self) -> None:
        self._event_bus.publish(
            DebugSnapshotEvent(
                category="foo.bar",
                data=self.get_state(),
                trigger="change",
            )
        )
```

## ファイル一覧

| ファイル | 責務 |
|----------|------|
| `iris/event/event_types.py` | DebugSnapshotEvent 定義 |
| `iris/event/tracer.py` | EventBusリングバッファ + category index |
| `iris/kernel/diagnostics.py` | SystemDiagnostics（auto-discovery, query, health, report） |
| `iris/kernel/config.py` | DebugConfig 設定モデル |
| `iris/kernel/commands/handler.py` | /debug 全サブコマンド実装 |
| `iris/event/event_bus.py` | EventBus に tracer 統合 |
| `iris/kernel/factory.py` | DI wiring |
| `debug_tools/cli.py` | 外部AIエージェント用 gRPC CLI |
