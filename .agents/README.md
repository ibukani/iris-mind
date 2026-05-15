# .agents

`.agents/` はコーディングエージェント向けの補助コンテキストを置く場所です。
恒久的なプロジェクト事実はここに重複保持せず、一次情報への導線だけを置きます。

## Files

- `project.md` : エージェント向けの短いプロジェクト要約。詳細は設計文書へのリンクで辿る。
- `skills/` : 繰り返し作業を標準化する Skill 定義。

## Source of truth

- プロジェクトルール: `AGENTS.md`
- アーキテクチャと設計判断: `docs/architecture.md`, `docs/adr/`
- 実装の履歴: Git commit / PR / Issue
- 一時的な作業メモ: 常設しない。必要時のみユーザーまたは作業ブランチ上で管理する。

## Rules

- `.agents/` に進捗ログやブランチ状態を常設しない
- ADR に残すべき決定は `docs/adr/` に記録する
- 運用手順の変更は対応する Skill と `AGENTS.md` を更新する
