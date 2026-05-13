# Iris セッションコンテキスト

このファイルはコーディングエージェントが現在のセッションや過去の決定事項を追跡するために使用します。

## プロジェクト状態

- 最新の安定動作バージョン: v0.1.0
- 開発フェーズ: アーキテクチャリファクタリング + 自律会話機能実装（Step 1）
- 現在のブランチ: `feature/arch-refactor`

## 重要な決定事項

| 日付 | 決定内容 |
|------|----------|
| 2026-05-12 | 機能変更時はドキュメント更新を必須とする（docs/*.md, memory/iris_profile.md, AGENTS.md, .agents/*.md） |
| 2026-05-13 | `.agent/` を `.agents/` に統合（skillsディレクトリが既に`.agents/`だったため） |
| 2026-05-12 | 1タスク完了ごとにgitコミットを必須とする。コード変更とドキュメント更新は同一コミットに含める |
| 2026-05-13 | アーキテクチャをヘキサゴナル + イベント駆動に刷新。`core/` → `iris/` へ移行 |
| 2026-05-13 | ガバナンスモデルを3層（Tier1自動/Tier2自己判断/Tier3AgentKernel介入）に決定 |
| 2026-05-13 | EventBusはインメモリ同期型で進行。将来分散対応可能にインターフェースを分離 |

## 既知の課題・注意点

- Ollama が動作していないと Iris は起動しない（`main.py:_ensure_config_models`）
- ChromaDB の ONNX 埋め込みは初回実行時にモデルを自動DLする（~80MB）
- `memory/data/iris_profile.md` は上限2KBの構造記憶のみ（話し方・性格は `persona_data.json` で動的管理）
- Windows環境を前提としている（パス区切り文字、シェル実行等）
- ProactiveEngineはまだ未実装。AgentState/EventBusのインターフェース確定後に着手

## 最近の作業履歴

| 日付 | 内容 |
|------|------|
| 2026-05-13 | 設計改善refactoring: ConversationService.process_input()を10フェーズに分割、model選択の副作用除去(set_model排除)、RAG二重実行解消、記憶ストアProtocol導入、cli.pyデッドコード削除(_ensure_ollama)、CommandContext型改善、プロンプトプレースホルダ統一 |
| 2026-05-13 | 自動モデル切替実装: configにfast_model追加、2段階分類(greeting/simple/qa/tool/complex)、context window管理。Qwen3.5:0.5b→Qwen3.5:9bの自動切替 |
| 2026-05-13 | 会話Compaction実装(Step1): core/context.py追加、ConfigManagerによる自動要約(compaction_threshold超過時)、/compactコマンド、conversation_summaryのシステムプロンプト注入 |
| ---- | ブランチ `feature/arch-refactor` を作成。新ディレクトリ構造 `iris/` を作成 |
| ---- | EventBus, AgentStateManager, ProactiveConfig を実装 |
