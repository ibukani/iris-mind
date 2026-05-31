---
name: iris-dev-workflow
description: |
  Use when making ordinary Iris code or documentation changes, especially MVP implementation,
  refactoring, deleting or changing existing functions, validation, and commit preparation.
  Do NOT use for plugin-specific creation/provider/hook details; use the dedicated plugin skills.
license: MIT
metadata:
  audience: developers
  workflow: iris-development
---

## Purpose

Iris の通常開発手順。MVP開発を妨げる保守的すぎる判断を避け、現在仕様に合わせて最小で動く形へ直す。

## Operating Rules

- 影響範囲は `rg` / `rg --files` で先に絞る。
- 関連ファイルは並列で読む。1ターンの読み込みは原則5ファイルまで。
- 実装が一次情報。ドキュメントやSkillと矛盾したら実装を確認して直す。
- 変更前の互換維持は要求がある時だけ行う。
- 仕様変更時は既存関数の変更・削除・名前変更を許可する。
- 不要になった関数、分岐、設定、テスト、docsは残さない。
- 既存実装の上に覆いかぶせない。現在仕様に合う形へ置換する。
- 抽象化は重複や複雑さを実際に減らす時だけ追加する。
- 将来のための拡張点、未使用hook、互換wrapperは作らない。

## Workflow

1. 要件確認。ブロッカーだけ質問。
2. 影響範囲調査。glob + grep。
3. 既存実装とテストを読む。
4. 現在仕様に合わない古い実装を削除・置換する。
5. 変更単位ごとに検証する。
6. `doc-sync` で更新漏れを確認する。
7. ユーザーが明示的に依頼した場合のみコミットする。

## MVP Decision Policy

- 「壊さない」より「今の仕様に正しく合う」を優先。
- public APIでも、ユーザーが仕様変更を求めたなら変更してよい。
- 移行コード、deprecated経路、旧形式パースは明示要求がない限り追加しない。
- テストは新仕様を固定する。旧仕様のテストは削除または書き換える。
- 大きな再設計より、小さく完結した置換を優先する。
- ただしデータ破壊、認証、外部送信、永続ストレージ削除、Git履歴変更は明示確認する。

## Python Rules

- Python 3.13+。
- 各ファイル先頭に `from __future__ import annotations`。
- `Optional[X]` ではなく `X | None`。
- `List[X]`, `Dict[K, V]`, `Union[X, Y]` ではなく `list[X]`, `dict[K, V]`, `X | Y`。
- 戻り値なしは `-> None`。
- import順: future → stdlib → 3rd party → `iris.`。
- `snake_case`, `PascalCase`, `UPPER_SNAKE_CASE`。
- ベア `except:` 禁止。`except Exception:` も最小限。
- リソースは `with`。
- コメントは意図が不明瞭な箇所だけ。
- f-string優先。

## Architecture Rules

- 全層は `iris/event/` を介して疎結合。
- `debug_tools/` は `iris/` に依存してよい。逆は禁止。
- PluginManager をロジッククラスに保持しない。依存はコンストラクタ注入。
- EventBus subscribe は原則 `handler.py` に置く。manager から直接 subscribe しない。
- 既存実装を構造ルールに完全一致させるだけの大規模リファクタは行わない。今回の変更範囲に関係する責務分離のみ行う。
- Plugin構造の詳細は `iris-plugin-structure` を読む。

## Validation

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

狭い変更では対象テストから始めてよい。最後に必要範囲を広げる。

## Docs

- コード変更後は `doc-sync` を読む。
- 削除した機能の説明は残さない。
- 「現在は」「従来は」「かつては」のような過去仕様メモを残さない。
- AGENTS.md に詳細を戻さない。参照だけにする。

## Git

- コミットはユーザーが明示的に依頼した場合のみ行う。
- メッセージは日本語。
- コード変更と必要なdocs更新は同一コミット。
