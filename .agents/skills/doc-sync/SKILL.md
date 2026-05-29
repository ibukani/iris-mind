---
name: doc-sync
description: |
  Use ONLY after making changes to iris code (new features, refactoring, architecture changes).
  Checks which docs need updating.
  Do NOT use: purely informational requests, no code changes made.
license: MIT
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
| 記憶システム変更 | `memory-layer.md` |
| EventBus変更 | `io-layer.md`, `event_types.py` |
| 意思決定/行動実行変更 | `agency-layer.md` |
| プロセス管理変更 | `kernel-layer.md` |
| 入出力変更 | `io-layer.md` |
| 設定変更 | `config.md` |
| 新機能全般 | 該当する文書がない場合は新規作成を検討 |

### 2. 自己プロフィール `.iris/config/iris_profile.md`

- 人格・口調・ルール記述の変更があった場合

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

ただし、`.agents/` はトークン効率を優先する。詳細な設計情報、進捗ログ、履歴は重複して書かず、一次情報への参照に留める。

### 5. Skills `.agents/skills/*/SKILL.md`

capability 追加パターンや開発ワークフローが変わった場合に更新。

## Procedure

1. 変更の内容を特定する
2. 上の表に照らして更新すべき文書をリストアップする
3. 各文書を順に読み、該当箇所を更新する
   - **削除された機能の記述は完全に消す。「現在は〜」「従来は〜」「かつては〜」のような過去形の遺残は一切残さない。ドキュメントは現状のみを記述する。**
4. `ruff check . && mypy .` で問題がないことを確認
5. コード変更とドキュメント更新を同一コミットに含める

## When to use me

- 機能追加・変更を行ったとき
- コミット前に更新漏れがないか確認したいとき
- プロジェクトルールを変更したとき
