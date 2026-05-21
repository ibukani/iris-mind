# Skill: iris-debug

## 概要

Iris Kernel のデバッグ基盤の使い方。

## デバッグ基盤アーキテクチャ

```
DebugSnapshotEvent(category, data, trigger)
    ↑ publish                                     EventTracer
    │                                              ┌─────────────────────┐
LimbicManager ── DebugSnapshotEvent ──────────────→ │ RingBuffer (500)   │
HippocampalManager ── DebugSnapshotEvent ─────────→ │ CategoryIndex      │
                                                    │ PerfCounters       │
SystemDiagnostics ── get_state() auto-discovery     └─────────────────────┘
    │                                                    ↑
    ├── kernel/manager.py                               EventBus.publish()
    ├── io/manager.py                                    (自動トレース)
    ├── memory/manager.py
    ├── limbic/manager.py                   debug_tools/cli.py
    ├── agency/manager.py                   ┌─────────────────────┐
    └── memory/personality/big_five.py      │ gRPC → /state       │
                                            │      → /events      │
                                            │      → /health      │
CommandHandler (/state, /events,            │      → /report      │
                /health, /report)           └─────────────────────┘
```

## 管理コンソールコマンド

| コマンド | 説明 |
|----------|------|
| `/state [<path>]` | システム状態を表示（path省略で全ツリー） |
| `/state limbic.emotion` | 特定パスの状態 |
| `/state limbic --history` | 状態変化の履歴 |
| `/state io --json` | JSON形式 |
| `/events [n]` | 直近n件のイベント |
| `/events 20 --type=DebugSnapshotEvent` | 型フィルタ |
| `/health` | 全コンポーネント健康診断 |
| `/report` | Markdownデバッグレポート生成 |

## パス一覧（状態ツリー）

- `kernel` — KernelManager.get_state() → global_state, layer_states
- `io` — IOManager.get_state() → listening, sessions
- `memory` — MemoryManager.get_state() → episodic, semantic count
- `limbic` — LimbicManager.get_state() → emotion (PAD), mood
- `agency` — AgencyManager.get_state() → planning, execution state
- `eventbus` — 統計情報（publish count, errors）

## カテゴリ（DebugSnapshotEvent history）

- `limbic.emotion` — 感情変化（trigger: message/decay/monitor/stimulus）
- `personality.big_five` — BigFive変化（trigger: reflection）

## gRPC CLI（外部AIエージェント用）

```bash
# 環境変数設定
export IRIS_HOST=127.0.0.1
export IRIS_PORT=9876
export IRIS_ACCESS_TOKEN=...

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
3. コマンド変更は不要 — path ベースで自動露出

## 実装コンポーネント一覧

| ファイル | 責務 |
|----------|------|
| `iris/event/event_types.py:DebugSnapshotEvent` | category + data のユニバーサルスナップショット |
| `iris/event/tracer.py` | EventBusリングバッファ + category index |
| `iris/kernel/diagnostics.py` | SystemDiagnostics（get_state auto-discovery, パスクエリ, health, レポート） |
| `iris/kernel/config.py:DebugConfig` | デバッグ設定 |
| `iris/kernel/commands/handler.py` | /state /events /health /report |
| `iris/event/event_bus.py` | EventBusにTracer統合 |
| `iris/kernel/factory.py` | 全DI wiring |
| `debug_tools/cli.py` | 外部AIエージェント用gRPC CLI |
