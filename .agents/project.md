# Iris Project Brief

このファイルは Iris 固有の概要と責務境界だけを素早く確認するための補助メモです。
通常開発ルールは `.agents/skills/iris-dev-workflow/SKILL.md`、設計判断は `docs/architecture.md` を一次情報にします。

## Scope

- Iris は Python 製のAIコンパニオン・アシスタントKernel。自律的行動・タスク実行を担い、最終的には自己進化を目指す。
- このリポジトリは Kernel 本体を扱う。UI や外部クライアントは別プロジェクトの責務。
- LLM provider は Ollama / OpenRouter などを設定で切り替える。
- モデルは単一モデル構成と role ベースの複数モデル構成をサポートする。
- 設定は `config.yaml`。`model.providers` でプロバイダ接続情報を定義し、`model.models[].provider` で各モデルのプロバイダを指定する。

## Main Modules

- `iris/kernel/`: プロセス管理、DI、Plugin lifecycle、Command。
- `iris/event/`: Global EventBus、イベント型、トレース。
- `iris/io/`: 入出力、gRPC、Session、Permission。
- `iris/account/`: ユーザー識別、外部ID連携、Presence。
- `iris/room/`: Room CRUD、membership、account連携。
- `iris/memory/`: sensory / short-term / long-term memory。
- `iris/limbic/`: emotion、mood、relationship。
- `iris/agency/`: planning、inhibition、execution。
- `iris/llm/`: provider、context window、tokenizer、prompt。
- `iris/tools/`: `@tool`、ToolRegistry、builtins。
- `iris/admin/`: CLI管理。

### 設計方針: Irisの個性とRoom

- **Irisは個として1体のみ存在する**
- Roomは会話場所を増やすためのシステム（Irisの複製ではない）
- 感情（Limbic）はグローバル。Roomごとの個別管理はしない
- 関係性（Relationship）はユーザー（Account）単位。Room単位ではない
- 複数Roomで同一ユーザーと会話しても、親密度等は共通

## Boundaries

- `iris/kernel/` はドメイン層。外部サービス実装を直接持ち込まない。
- `iris/llm/`, `iris/tools/` は kernel へ注入されるインフラ層。
- `iris/io/`, `iris/agency/`, `iris/memory/`, `iris/event/`, `iris/account/`, `iris/room/` は kernel から分離された独立層。
- 全層は EventBus (`iris/event/`) を介して疎結合。
- `debug_tools/` は `iris/` に依存してよいが、`iris/` から `debug_tools/` へ依存しない。
- IPC とプロセス設計の詳細は `docs/architecture.md` を読む。

## Workflows

- 通常開発: `.agents/skills/iris-dev-workflow/SKILL.md`
- capability 追加: `.agents/skills/capability-pattern/SKILL.md`
- ドキュメント更新確認: `.agents/skills/doc-sync/SKILL.md`
- 設計変更: `docs/architecture.md` に残し、必要な設計文書だけ更新する。

## Context Rules

- ブランチ状態、完了済みタスク、過去の決定ログはここに書かない。
- 実装前に必要なファイルだけ読む。大きい設計文書は該当セクションから確認する。
- 変更後は `AGENTS.md` と `.agents/README.md` の読み込み方針と矛盾しないか確認する。
- 詳細なディレクトリツリーをここに増やさない。必要なら `rg --files iris` で実コードを見る。
