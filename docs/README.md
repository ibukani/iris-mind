# Iris ドキュメント一覧

## ドキュメント一覧

| ファイル | 内容 |
|---|---|
| [`architecture.md`](./architecture.md) | 全体アーキテクチャ設計書 — v0.3 Kernel-only |
| [`agent-state.md`](./agent-state.md) | AgentState 状態遷移設計書 — 6状態と遷移テーブル |
| [`event-bus.md`](./event-bus.md) | EventBus インターフェース仕様書 — Protocol抽象（Kernel内部専用） |
| [`ipc-spec.md`](./ipc-spec.md) | IPC プロトコル仕様 — Named Pipe, シリアライズ, 接続ライフサイクル |
| [`proactive-engine.md`](./proactive-engine.md) | ProactiveEngine 設計仕様 — 自律発話の全アルゴリズム |
| [`agent-kernel.md`](./agent-kernel.md) | AgentKernel 設計仕様 — イベント統括・Tier3異常検知 |
| [`memory-manager.md`](./memory-manager.md) | MemoryManager 設計仕様 — 記憶操作の一元管理 |
| [`config.md`](./config.md) | Config 設定一覧 — 全フィールドとデフォルト値 |
| [`conversation-service.md`](./conversation-service.md) | ConversationService 設計仕様 — 会話処理パイプライン |
| [`commands.md`](./commands.md) | コマンドシステム仕様 — スラッシュコマンド一覧と拡張方法 |

### Architecture Decision Records

| ファイル | 内容 |
|---|---|
| [`adr/001-3-process-architecture.md`](./adr/001-3-process-architecture.md) | 3-Process分解の決定記録 — IPC方式, Phase順, トレードオフ |

## 設計背景

Iris は Kernel-only プロジェクトとして設計されている。
Kernel は Named Pipe で制御インターフェースを公開し、CLI 等の UI は別プロジェクトが提供する。

### 主要設計決定

1. **Kernel-only 構成** — このリポジトリは Kernel 本体のみ。CLI 等のアダプターは外部プロジェクト
2. **イベント駆動** — `EventBus` でコンポーネント間を疎結合に接続
3. **IPC: Named Pipes** — Kernel は `Listener`（サーバー）として起動、外部 Client の接続を待つ
4. **自律発話** — `ProactiveEngine` が3層ガバナンスで自発的に会話を開始
5. **管理コンソール** — `main.py` の Supervisor が stdin 経由で `/status`, `/shutdown` を受け付ける

### Architecture Decision Records

設計上の重要な決定は `adr/` ディレクトリに記録する。
