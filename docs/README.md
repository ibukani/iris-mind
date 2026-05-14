# Iris ドキュメント一覧

## ドキュメント一覧

| ファイル | 内容 |
|---|---|
| [`architecture.md`](./architecture.md) | 全体アーキテクチャ設計書 — v0.3 3-Process分解 |
| [`agent-state.md`](./agent-state.md) | AgentState 状態遷移設計書 — 6状態と遷移テーブル |
| [`event-bus.md`](./event-bus.md) | EventBus インターフェース仕様書 — Protocol抽象 + IPC |
| [`ipc-spec.md`](./ipc-spec.md) | IPC プロトコル仕様 — Named Pipe, シリアライズ, 制御イベント |
| [`migration-roadmap.md`](./migration-roadmap.md) | 移行ロードマップ — Phase 0-4 の詳細計画 |
| [`proactive-engine.md`](./proactive-engine.md) | ProactiveEngine 設計仕様 — 自律発話の全アルゴリズム |
| [`agent-kernel.md`](./agent-kernel.md) | AgentKernel 設計仕様 — イベント統括・Tier3異常検知 |
| [`memory-manager.md`](./memory-manager.md) | MemoryManager 設計仕様 — 記憶操作の一元管理 |
| [`config.md`](./config.md) | Config 設定一覧 — 全フィールドとデフォルト値 |
| [`conversation-service.md`](./conversation-service.md) | ConversationService 設計仕様 — 会話処理パイプライン |

### Architecture Decision Records

| ファイル | 内容 |
|---|---|
| [`adr/001-3-process-architecture.md`](./adr/001-3-process-architecture.md) | 3-Process分解の決定記録 — IPC方式, Phase順, トレードオフ |

## 設計背景

Iris v0.2 → v0.3 では単一プロセスから3プロセス（Input / Kernel / Output）への移行を計画している。
詳細は `adr/001-3-process-architecture.md` および `migration-roadmap.md` を参照。

### 主要設計決定

1. **ヘキサゴナルアーキテクチャ** — `adapters/` と `iris/kernel/` の分離（v0.2から継続）
2. **イベント駆動** — `EventBus` でコンポーネント間を疎結合に接続
3. **3-Process分解** — Input / Kernel / Output を別プロセスで動作（v0.3目標）
4. **IPC: Named Pipes** — Windows 環境で `AF_PIPE` を使用
5. **自律発話** — `ProactiveEngine` が3層ガバナンスで自発的に会話を開始

### Architecture Decision Records

設計上の重要な決定は `adr/` ディレクトリに記録する。
