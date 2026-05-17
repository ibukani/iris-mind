# Iris ドキュメント一覧

## ドキュメント一覧

| ファイル | 内容 |
|---|---|
| [`architecture.md`](./architecture.md) | **v2 全体アーキテクチャ設計書** — 脳科学ベース層分割、C4図、イベントフロー、状態管理 |
| [`agency-layer.md`](./agency-layer.md) | **Agency 層（前頭前野+基底核+運動野）** — 意思決定(planning) と行動実行(execution) |
| [`io-layer.md`](./io-layer.md) | **IO 層（視床）** — TCP入出力、セッション管理、認証、EventBusマッピング |
| [`kernel-layer.md`](./kernel-layer.md) | **Kernel 層（脳幹+視床下部）** — プロセス管理、DI、CommandHandler、TimerTick |
| [`memory-layer.md`](./memory-layer.md) | **Memory 層（感覚野+海馬+皮質）** — 感覚バッファ、エピソード/意味記憶、海馬整理、人格 |
| [`config.md`](./config.md) | Config 設定一覧 — 全フィールドとデフォルト値 |
| [`ipc-spec.md`](./ipc-spec.md) | IPC プロトコル仕様 — TCP, シリアライズ, 接続ライフサイクル |

## 設計背景

Iris v2 は脳科学・神経科学の構造を参考にした層分割アーキテクチャを採用する（参考マッピングの正確性については各層設計書の注記を参照）。

各層は独立した責務を持ち、`iris/event/`（神経路）のグローバル EventBus を介して疎結合する。
詳細は [`architecture.md`](./architecture.md) および各層ドキュメントを参照。

### 主要設計決定

1. **脳科学ベース層分割** — 脳幹(Kernel)、視床(IO)、感覚野+海馬(Memory)、前頭前野+基底核(Agency)、神経路(Event)
2. **イベント駆動** — Global EventBus で全層を疎結合。各層は publish/subscribe のみ
3. **IPC: TCP** — Kernel は `TcpListener` で1ポートの待受、外部 Client の接続を待つ
4. **Internal Bus** — Agency 層内の planning↔execution 通信は内部 EventBus を使用
5. **DI コンテナ** — Factory (`kernel/factory.py`) のみ全層のインスタンス生成を行う

### Architecture Decision Records

設計上の重要な決定は `docs/adr/` に記録する。
