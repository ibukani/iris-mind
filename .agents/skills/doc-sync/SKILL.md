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
| アーキテクチャ変更 | `02_architecture.md` |
| 記憶システム変更 | `03_memory_system.md` |
| 自己改変機能変更 | `04_self_mod.md` |
| 概念・設計思想変更 | `01_concept.md` |
| 新機能全般 | 該当する文書がない場合は新規作成を検討 |

### 2. 構造記憶 `memory/data/iris_profile.md`

- `## My Capabilities` セクション：capability の追加・削除・名称変更があった場合
- `## Known Structure` セクション：ディレクトリ構成やコアファイル構成が変わった場合

### 3. AGENTS.md

- コーディング規約の変更
- lint/typecheck コマンドの変更
- ディレクトリ構成の更新
- ドキュメント更新義務の変更
- git コミットルールの変更

### 4. `.agent/*.md`

以下の内容が変わった場合に更新：
- プロジェクト概要 (`.agent/project.md`)
- セッションコンテキスト (`.agent/context.md`)
- タスク管理 (`.agent/tasks.md`)

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
