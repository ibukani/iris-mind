# .agents

`.agents/` はコーディングエージェント向けの補助コンテキストを置く場所です。
恒久的なプロジェクト事実はここに重複保持せず、一次情報への導線だけを置きます。

## Context Budget

- 常時読むのは `AGENTS.md` だけにする
- このファイルは `.agents/` の役割確認が必要なときだけ読む
- `project.md` はプロジェクト概要や責務境界を確認するときだけ読む
- `skills/*/SKILL.md` は該当作業を行うときだけ読む
- 複数の Skill が該当する場合は、より具体的な Skill を優先する
- `docs/` は関連する設計判断が必要なときに対象ファイルだけ読む
- Git 履歴やテスト結果は必要な範囲だけ取得し、過去ログを `.agents/` に複製しない

## Skill Priority

重複しそうな場合の優先順位:

1. capability / tool 追加: `skills/capability-pattern/SKILL.md`
2. LLM provider / store backend / sub-plugin 追加: `skills/iris-plugin-provider/SKILL.md`
3. Hook追加・HookPoint追加: `skills/iris-plugin-hook/SKILL.md`
4. 新規トップレベルPlugin作成: `skills/iris-plugin-create/SKILL.md`
5. 既存Plugin構造整理: `skills/iris-plugin-structure/SKILL.md`
6. 通常開発: `skills/iris-dev-workflow/SKILL.md`
7. docs更新確認: `skills/doc-sync/SKILL.md`

## Files

- `project.md` : エージェント向けの最小プロジェクト要約。詳細は設計文書へのリンクで辿る。
- `skills/` : 繰り返し作業を標準化する Skill 定義。

## Source of truth

- エージェント入口: `AGENTS.md`
- 通常開発ルール: `skills/iris-dev-workflow/SKILL.md`
- アーキテクチャと設計判断: `docs/architecture.md`
- 実装の履歴: Git commit / PR / Issue
- 一時的な作業メモ: 常設しない。必要時のみユーザーまたは作業ブランチ上で管理する。

## Rules

- `.agents/` に進捗ログやブランチ状態を常設しない
- 設計判断は `docs/architecture.md` に記録する（必要に応じて `docs/adr/` を新設可）
- 運用手順の変更は対応する Skill を更新し、`AGENTS.md` は参照先だけ必要最小限で更新する
- 要約よりも参照先を優先し、同じ事実を複数ファイルに書かない
