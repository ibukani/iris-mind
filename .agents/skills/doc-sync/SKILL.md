---
name: doc-sync
description: |
  Use after making changes to iris code or project rules
  (new features, refactoring, architecture changes, AGENTS/skills workflow changes).
  Checks which docs need updating.
  Do NOT use: purely informational requests with no file changes.
license: MIT
metadata:
  audience: developers
  workflow: iris-docs
---

## What I do

機能追加・変更・プロジェクトルール変更を行った際に、更新が必要なドキュメントを洗い出し、更新するワークフローです。

## Documents to check

### 1. 設計ドキュメント `docs/*.md`

変更内容に応じて該当する文書を更新：

| 変更対象 | 更新すべき文書 |
|----------|---------------|
| アーキテクチャ変更 | `docs/architecture.md` |
| 記憶システム変更 | `docs/memory-layer.md`, `docs/how-it-works/02-memory-system.md` |
| EventBus変更 | `docs/how-it-works/01-eventbus.md`, `docs/architecture.md`, 関連する層ドキュメント |
| 意思決定/行動実行変更 | `docs/agency-layer.md`, `docs/how-it-works/05-decision-making.md`, `docs/how-it-works/08-execution-pipeline.md` |
| プロセス管理変更 | `docs/kernel-layer.md` |
| 入出力変更 | `docs/io-layer.md`, `docs/external/*.md` |
| 設定変更 | `docs/config.md` |
| モデルルーティング変更 | `docs/how-it-works/11-model-routing.md`, `docs/config.md` |
| 新機能全般 | 該当する文書がない場合は新規作成を検討 |

実装側では、変更に応じて `iris/event/event_types.py` など関連コードとの整合も確認する。

### 2. 自己プロフィール `.iris/config/iris_profile.md`

- 人格・口調・ルール記述の変更があった場合
- Irisの自己認識、使用可能能力、ふるまいに影響する capability 変更があった場合
- 内部実装だけの変更では更新しない

### 3. AGENTS.md

- エージェント入口としての参照先変更
- 常時読むファイル方針の変更
- 最優先の行動原則変更

詳細なコーディング規約、ワークフロー、ディレクトリ構成は AGENTS.md に戻さず、該当Skillか `.agents/project.md` に置く。

### 4. `.agents/README.md`, `.agents/project.md`

以下の内容が変わった場合に更新：

- エージェント向け導線 (`.agents/README.md`)
- プロジェクト概要 (`.agents/project.md`)
- Skill 選択ルールや責務境界

ただし、`.agents/` はトークン効率を優先する。詳細な設計情報、進捗ログ、履歴は重複して書かず、一次情報への参照に留める。

### 5. Skills `.agents/skills/*/SKILL.md`

capability 追加パターン、開発ワークフロー、MVP判断、Plugin規約が変わった場合に更新。

## Procedure

1. 変更の内容を特定する
2. 上の表に照らして更新すべき文書をリストアップする
3. 各文書を順に読み、該当箇所を更新する
   - **削除された機能の記述は完全に消す。「現在は〜」「従来は〜」「かつては〜」のような過去形の遺残は一切残さない。ドキュメントは現状のみを記述する。**
4. 変更種別に応じて検証する

検証のみ:

```bash
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

修正を許可されている場合:

```bash
uv run ruff check --fix .
uv run ruff format .
```

5. ユーザーが明示的に依頼した場合のみ、コード変更とドキュメント更新を同一コミットに含める

## When to use me

- 機能追加・変更を行ったとき
- コミット前に更新漏れがないか確認したいとき
- プロジェクトルールを変更したとき
