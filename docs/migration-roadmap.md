# Iris v0.3 移行ロードマップ

## 概要

v0.2（単一プロセス）から v0.3（3-Process分解）への移行計画。

現状: **Phase 0 〜 Phase 3 のコア実装は完了**。残るは Phase 4（マルチ入力）および
エッジケース対応・テスト拡充。

## Phase 一覧

| Phase | 内容 | 状態 | 成果物 |
|-------|------|------|--------|
| Phase 0 | EventBus Protocol 化 + イベントシリアライズ + trace_id | ✅ 完了 | `EventBusProtocol`, `Event.to_dict/from_dict`, `ReplayableTransport` |
| Phase 1 | Output Process 分離 | ✅ 完了 | `OutputBridge`, `PipeServer`/`PipeClient`, `debug_tools/cli/output_main.py`, `renderer.py` |
| Phase 2 | Input Process 分離 + ProactiveResponseTracker移植 | ✅ 完了 | `InputBridge`, `CommandRouter`, `ProactiveResponseTracker`, `debug_tools/cli/input_main.py` |
| Phase 3 | Controller プロセス導入 | ✅ 完了 | `IrisController`（起動・監視・ヘルスチェック・自動再起動） |
| Phase 4 | マルチ入力ソース対応 | ⏳ 未着手 | TCP Input, WebSocket, Discord Bot |

## Phase 0: EventBus Protocol 化

### 変更内容
- `EventBusProtocol`（Protocol クラス）を導入
- 全イベントクラスを `iris/kernel/event.py` に集約
- `trace_id`（UUID4）を全イベントに追加
- `to_dict()` / `from_dict()` による JSON シリアライズ対応
- `ReplayableTransport` によるデバッグ用記録・再生

### 後方互換性
- `EventBus` 具象クラスは従来の API を維持
- 既存の全テスト（179件）が修正なしで通過

## Phase 1: Output Process 分離

### 責務
- イベント受信 → 表示（Rich Live レンダリング）
- Kernel からの切断に強健（再接続可能）
- 単方向通信（Kernel → Output）

### 実装
- `OutputBridge`: Kernel 内部で EventBus の表示用イベントを購読し、Pipe に中継
- `output_main.py`: Output プロセスのエントリポイント
- `renderer.py`: Rich を使った表示ロジック

## Phase 2: Input Process 分離

### 責務
- ユーザー入力受付 → Pipe 経由で Kernel に送信
- stateless（入力転送のみ）

### 実装
- `InputBridge`: Kernel 内部で Input Pipe を待受 → `EventBus.publish()`
- `CommandRouter`: UserInputEvent を購読し、`/` コマンドを処理
- `ProactiveResponseTracker`: 自発発話へのユーザー反応を評価（Kernel 内）
- `input_main.py`: Input プロセスのエントリポイント

### 従来からの変更点
- CLIAdapter にあった `_check_proactive_response()` → `ProactiveResponseTracker` に
- 従来の `server.py`（CLIAdapter）は `debug_tools/cli/server.py` として存続（単一プロセス互換用）

## Phase 3: Controller プロセス導入

### 責務
- Kernel プロセス内で動作（別プロセスではない）
- Input/Output プロセスの起動・監視・自動再起動
- シャットダウンシーケンスの統括

### 実装
- `IrisController`: 全プロセスのライフサイクル管理
  - `launch()`: コンポーネント組立 + サブプロセス起動
  - `shutdown()`: 正常終了 + リソース解放
  - `_check_health()`: 5秒間隔の死活監視 + 自動再起動（最大10回）

## テスト戦略

| 対象 | 方式 |
|------|------|
| EventBus | FakeEventBus（インメモリ Protocol 準拠） |
| Pipe 通信 | FakePipeConnection（インメモリバイト転送） |
| IrisController | FakeSubprocess（プロセス代替）+ FakePipe |
| E2E | 単一プロセスモード（全コンポーネントを同一プロセスで起動） |
