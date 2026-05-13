# Iris ドキュメント一覧

## 最新ドキュメント（v0.2）

| ファイル | 内容 |
|---|---|
| [`architecture.md`](./architecture.md) | 全体アーキテクチャ設計書 — ヘキサゴナル＋イベント駆動 |
| [`agent-state.md`](./agent-state.md) | AgentState 状態遷移設計書 — 6状態と遷移テーブル |
| [`event-bus.md`](./event-bus.md) | EventBus インターフェース仕様書 — イベント種別と配信 |
| [`proactive-engine.md`](./proactive-engine.md) | ProactiveEngine 設計仕様 — 自律発話の全アルゴリズム |

## 旧ドキュメント（DEPRECATED）

| ファイル | 対応先 | 備考 |
|---|---|---|
| [`01_concept.md`](./01_concept.md) | `architecture.md` | 概念部分は新設計書に統合済み。先頭にDEPRECATEDスタブあり |
| [`02_architecture.md`](./02_architecture.md) | `architecture.md` | 旧アーキテクチャ図。新版で完全リプレイス済み。先頭にDEPRECATEDスタブあり |
| [`03_memory_system.md`](./03_memory_system.md) | 現行維持 | MemoryManager v0.2 追記あり |
| [`04_self_mod.md`](./04_self_mod.md) | 保留 | 機能未実装 |

## 設計背景

Iris v0.2 の設計理由については `.agents/context.md` を参照してください。

### 主要設計決定

1. **ヘキサゴナルアーキテクチャ** — `adapters/` と `kernel/` の分離により、UI差し替えが安全に可能
2. **イベント駆動** — `EventBus` でコンポーネント間を疎結合に接続
3. **自律発話** — `ProactiveEngine` が3層ガバナンス（Tier1自動/Tier2自己判断/Tier3介入）で自発的に会話を開始
4. **段階的移行** — 旧 `core/` をラッパーで維持しつつ、新 `iris/` 配下に機能を移行