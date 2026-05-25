---
name: layer-refactoring
description: Iris 層内リファクタリング（ファイル移動・分割・統合・リネーム）の最小ワークフロー
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: iris-refactoring
---

## Purpose

層内の構造変更（ファイル移動・分割・統合・リネーム・クラス名変更）をするときだけ読む。
全コミットの43%がリファクタリングであり、特に `iris/agency/`（37%）と `iris/memory/`（16%）で頻発する。

## Steps

### 1. 影響範囲を調査する

```powershell
# 移動元ファイルの全参照を洗い出す
rg "from iris\.<old_path>|from iris\.<old_module>|import iris\.<old_module>" --type py
rg "<OldClassName>" --type py

# テストでの参照
rg "<old_name>" tests/ --type py

# docs での参照
rg "<old_name>" docs/ --type md
rg "<old_name>" AGENTS.md
rg "<old_name>" .agents/ --type md

# 設定・プロファイルでの参照
rg "<old_name>" .iris/ --type md
rg "<old_name>" config.yaml
```

チェックすべき箇所:
- `kernel/factory.py`（DIコンテナ。層追加/削除/移動時は必ず更新）
- `__init__.py`（公開API変更時）
- `conftest.py`（FakeStore/FakeProvider/Fixture定義）
- `EventBus` event_types.py（イベント型追加/削除時）
- 全 `from` / `import` 参照
- `docs/*.md`, `docs/adr/*.md`, `docs/how-it-works/*.md`
- `AGENTS.md`（ディレクトリ構成変更時）
- `.agents/project.md`、`.agents/skills/*/SKILL.md`
- `.iris/data/iris_profile.md`（capability説明変更時）
- `config.yaml`（設定キー変更時）

### 2. 作業計画を立てる

変更の種類に応じて順序を決める:

| 変更種別 | 推奨順序 |
|----------|---------|
| ファイル移動 | ①移動→②全import更新→③__init__.py→④空になった元ファイル削除 |
| ファイル分割 | ①新ファイル作成→②import経路確立→③元ファイルから切り出し→④参照更新 |
| ファイル統合 | ①import経路確立→②コード移行→③元ファイル削除→④参照一斉置換 |
| クラス名変更 | ①クラス定義変更→②全参照一括置換（replaceAll） |
| ディレクトリ再編 | ①__init__.py整備→②ファイル移動→③全import更新→④factory.py更新 |

### 3. 実行する（1論理変更 = 1編集単位）

```powershell
# ファイル移動（git mv で履歴追跡を維持）
git mv iris/old/path/file.py iris/new/path/file.py
```

```python
# import 更新（全ファイル一括）
# 例: from iris.llm.llm_bridge → from iris.llm.bridge
```

```python
# __init__.py 更新（公開API再エクスポート）
from iris.new_module import NewClass

__all__ = ["NewClass"]
```

### 4. テストを整合させる

Iris のテスト原則:
- **LLM 実通信禁止。** 全テストは Fake 実装で行う（`tests/conftest.py` 参照）
- **Fake 実装パターン:** `FakeLLMProvider`, 6種のFakeStore (`FakeEpisodicStore`, `FakeSemanticStore`, `FakeVectorStore`, `FakeMemoryManager`, `FakePersonaData`, `FakePersonaProfile`), `FakeAgentsMdStore`, `FakeContextManager`, `FakeToolExecutionEngine`, `FakeReflexion`, `FakePersonality`
- 新しい Store/Manager/Provider を追加したら、対応する Fake クラスを `conftest.py` に追加し、`@pytest.fixture` も併せて定義する

テストファイルの扱い:
- テストファイルの移動: 元ファイルと同じディレクトリ構成を保つ（`tests/` 配下は `iris/` の構造をミラー）
- `conftest.py` の Fixture/Fake 定義を更新（Store追加時は必ず Fake と fixture を追加）
- テスト内の import / クラス名を更新
- リファクタリングで新ロジックが増えた場合はテストを追加する。パターンは既存の同層テストに従う

検証:
```powershell
uv run pytest tests/ -q
```

### 5. ドキュメントを同期する

```powershell
# パス・ファイル名・クラス名の変更をdocsに反映
rg "<old_path|old_name>" docs/ --type md
rg "<old_path|old_name>" .agents/ --type md
rg "<old_path|old_name>" AGENTS.md

# アーキテクチャ変更時は docs/architecture.md または docs/adr/ に記録
# .iris/data/iris_profile.md も確認
```

ドキュメント更新漏れ確認は `.agents/skills/doc-sync/SKILL.md` を参照。

### 6. 検証してコミットする

```powershell
# lint
uv run ruff check --fix .
uv run ruff format --check .

# type check
uv run mypy .

# test
uv run pytest tests/ -q

# コミット（コード+docs 同一コミットに含める）
git add .
git commit -m "refactor: <変更内容の簡潔な説明>"
```

## Rules

- `git mv` を使いファイル履歴を維持する（copy/delete ではない）
- import 更新は全ファイル漏れなく。rg で移動元の参照がゼロになることを確認してから削除する
- 1コミットに複数種のリファクタリングを混ぜない
- クラス名変更の後方互換エイリアスは不要（Irisは社内専用、breaking change 許容）
- `docs/architecture.md` のディレクトリツリーも忘れず更新する
