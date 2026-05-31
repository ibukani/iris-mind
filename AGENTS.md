# Iris Agent Entry

## 最優先

- AGENTS.md は入口。詳細をここに増やさない。
- 常時読むのはこのファイルだけ。
- 必要になった時だけ参照先を読む。
- 実装が正。ドキュメントと矛盾したら実装を確認し、必要ならドキュメントを直す。

## Response Style

- 挨拶や冗長な前置きは省く。
- 回答は簡潔にする。
- ただし、変更理由、リスク、検証結果、未確認事項は省略しない。

## Safety

- データ破壊、認証、外部送信、永続ストレージ削除、Git履歴変更は明示確認なしに行わない。
- コミットはユーザーが明示的に依頼した場合のみ行う。

## 作業姿勢

- MVP優先。今の仕様を最短で動かす。
- 仕様変更時は既存関数・既存APIの温存を優先しない。
- 不要な関数、互換層、古い分岐、死んだテスト、古い記述は削除する。
- 変更や削除を怖がらない。現在の仕様に合う小さな設計へ置き換える。
- 上書き実装、暫定ラッパー、過剰抽象化、将来用フックを避ける。
- 不明点はブロッカーだけ質問。それ以外は実装から判断する。

## 参照先

- プロジェクト要約・責務境界: `.agents/project.md`
- 通常開発・MVP判断・コード規約・検証・git: `.agents/skills/iris-dev-workflow/SKILL.md`
- 新規トップレベルPlugin: `.agents/skills/iris-plugin-create/SKILL.md`
- Hook追加: `.agents/skills/iris-plugin-hook/SKILL.md`
- Provider / sub-plugin追加: `.agents/skills/iris-plugin-provider/SKILL.md`
- Plugin構造整理: `.agents/skills/iris-plugin-structure/SKILL.md`
- 図・Mermaid: `.agents/skills/iris-visualize/SKILL.md`
- ドキュメント同期: `.agents/skills/doc-sync/SKILL.md`
- capability / tool追加: `.agents/skills/capability-pattern/SKILL.md`
- 設計詳細: `docs/`

## 読むタイミング

- 作業開始: 必要なら `.agents/project.md`
- コード変更: `iris-dev-workflow`
- Plugin関連: 該当Plugin skill
- docs更新判断: `doc-sync`
- 設計判断: 関連する `docs/*.md` のみ

## コマンド

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

## Git

- コミットはユーザーが明示的に依頼した場合のみ行う。
- 日本語メッセージ。
- コード変更と必要なdocs更新は同一コミット。
