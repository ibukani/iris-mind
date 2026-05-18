# Iris Project Brief

このファイルは `AGENTS.md` を読んだ後に、Iris 固有の責務境界だけを素早く確認するための補助メモです。
詳細な構成、コマンド、ルールは `AGENTS.md`、設計判断は `docs/architecture.md` と `docs/adr/` を一次情報にします。

## Scope

- Iris は Python 製の自律型 AI アシスタント Kernel。
- このリポジトリは Kernel 本体を扱う。UI や外部クライアントは別プロジェクトの責務。
- LLM provider は Ollama / OpenRouter を設定で切り替える。
- モデルは単一モデル構成と role ベースの複数モデル構成をサポートする。

## Boundaries

- `iris/kernel/` はドメイン層。外部サービス実装を直接持ち込まない。
- `iris/llm/`, `iris/tools/` は kernel へ注入されるインフラ層。
- `iris/memory/` は記憶系層。過去のインフラ層から昇格。
- `iris/limbic/` は感情系層（大脳辺縁系）。EventBus 経由で全層と疎結合。
- `iris/io/`, `iris/agency/`, `iris/event/` は kernel から分離された独立層。
- 全層は EventBus (`iris/event/`) を介して疎結合。
- `limbic/` → `memory/`（感情タグ）, `limbic/` → `agency/`（感情変調）のインターフェースを持つ。
- `debug_tools/` は `iris/` に依存してよいが、`iris/` から `debug_tools/` へ依存しない。
- IPC とプロセス設計の詳細は `docs/architecture.md` と `docs/adr/` を読む。

## Workflows

- capability 追加: `.agents/skills/capability-pattern/SKILL.md`
- ドキュメント更新確認: `.agents/skills/doc-sync/SKILL.md`
- 設計変更: `docs/adr/` に残し、必要な設計文書だけ更新する。

## Context Rules

- ブランチ状態、完了済みタスク、過去の決定ログはここに書かない。
- 実装前に必要なファイルだけ読む。大きい設計文書は該当セクションから確認する。
- 変更後は `AGENTS.md` と `.agents/README.md` の読み込み方針と矛盾しないか確認する。
