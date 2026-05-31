# Iris ドキュメント一覧

## ドキュメント一覧

### 外部開発者向け（Client接続）

| ファイル | 内容 |
|---|---|---|
| [`client-guide.md`](./external/client-guide.md) | **Iris Client Guide** — 応答パターン、自発発話、コマンド、クイックリファレンス |
| [`protocol-spec.md`](./external/protocol-spec.md) | **IPCプロトコル仕様** — ワイヤー形式、認証、プロトコル概要（データ型定義→[types](./external/protocol-types.md)、接続シーケンス→[flows](./external/protocol-flows.md)) |

### 内部設計（アーキテクチャ理解向け）

| ファイル | 内容 |
|---|---|---|
| [`architecture.md`](./architecture.md) | **全体アーキテクチャ設計書** — 脳科学ベース層分割、C4図、イベントフロー、状態管理 |
| [`agency-layer.md`](./agency-layer.md) | **Agency 層（前頭前野+基底核+運動野）** — 意思決定(planning) と行動実行(execution) |
| [`io-layer.md`](./io-layer.md) | **IO 層（視床）** — gRPC入出力、セッション管理、認証、EventBusマッピング |
| [`kernel-layer.md`](./kernel-layer.md) | **Kernel 層（脳幹）** — プロセス管理、PluginManager、CommandHandler、TimerTick |
| [`memory-layer.md`](./memory-layer.md) | **Memory 層（感覚野+皮質）** — 感覚バッファ、短期/長期記憶、GoalStore長期目標 |
| [`config.md`](./config.md) | Config 設定一覧 — 全フィールドとデフォルト値 |
| [`how-it-works/`](./how-it-works/) | **動作原理の詳細解説** — 計算式・条件分岐・Mermaid図を網羅（6ファイル） |

## 設計背景

Iris は脳科学・神経科学の構造を参考にした層分割アーキテクチャを採用する（参考マッピングの正確性については各層設計書の注記を参照）。

各層は独立した責務を持ち、`iris/event/`（神経路）のグローバル EventBus を介して疎結合する。
詳細は [`architecture.md`](./architecture.md) および各層ドキュメントを参照。

### 主要設計決定

1. **脳科学ベース層分割** — 脳幹(Kernel)、視床(IO)、感覚野+皮質(Memory)、前頭前野+基底核+運動野(Agency)、神経路(Event)
2. **イベント駆動** — Global EventBus で全層を疎結合。各層は publish/subscribe のみ
3. **IPC: gRPC** — Kernel は `GrpcListener` で1ポートの待受、外部 Client の接続を待つ
4. **Internal Bus** — Agency 層内の planning↔execution 通信は内部 EventBus を使用
5. **PluginManager DI** — `PluginManager` が全層の構築・依存解決・ライフサイクル管理を行う
