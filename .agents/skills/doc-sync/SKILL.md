---
name: doc-sync
description: Iris プロジェクトの変更時に更新すべきドキュメントをチェックするワークフロー
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: iris-docs
---

## What I do

機能追加・変更を行った際に、更新が必要なドキュメントを漏れなく洗い出し、更新するワークフローです。

## Documents to check

### 1. 設計ドキュメント `docs/*.md`

変更内容に応じて該当する文書を更新：

| 変更対象 | 更新すべき文書 |
|----------|---------------|
| アーキテクチャ変更 | `architecture.md` |
| 記憶システム変更 | `memory-manager.md` |
| EventBus変更 | `event-bus.md` |
| AgentState変更 | `agent-state.md` |
| 自発発話変更 | `proactive-engine.md` |
| AgentKernel変更 | `agent-kernel.md` |
| ConversationService変更 | `conversation-service.md` |
| 設定変更 | `config.md` |
| 新機能全般 | 該当する文書がない場合は新規作成を検討 |

### 2. 構造記憶 `.iris/data/iris_profile.md`

- `## My Capabilities` セクション：capability の追加・削除・名称変更があった場合
- `## Known Structure` セクション：ディレクトリ構成やコアファイル構成が変わった場合

### 3. AGENTS.md

- コーディング規約の変更
- lint/typecheck コマンドの変更
- ディレクトリ構成の更新
- ドキュメント更新義務の変更
- git コミットルールの変更

### 4. `.agents/README.md`, `.agents/project.md`

以下の内容が変わった場合に更新：
- エージェント向け導線 (`.agents/README.md`)
- プロジェクト概要 (`.agents/project.md`)

### 5. Skills `.opencode/skills/*/SKILL.md`

capability 追加パターンや開発ワークフローが変わった場合に更新。

## Procedure

1. 変更の内容を特定する
2. 上の表に照らして更新すべき文書をリストアップする
3. 各文書を順に読み、該当箇所を更新する
4. `ruff check . && mypy .` で問題がないことを確認
5. コード変更とドキュメント更新を同一コミットに含める

## When to use me

- 機能追加・変更を行ったとき
- コミット前に更新漏れがないか確認したいとき
- プロジェクトルールを変更したとき
