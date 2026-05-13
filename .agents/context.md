# Iris セッションコンテキスト

このファイルはコーディングエージェントが現在のセッションや過去の決定事項を追跡するために使用します。

## プロジェクト状態

- 最新の安定動作バージョン: v0.1.0
- 開発フェーズ: 初期開発（基本機能実装完了、拡張フェーズ）

## 重要な決定事項

| 日付 | 決定内容 |
|------|----------|
| 2026-05-12 | 機能変更時はドキュメント更新を必須とする（docs/*.md, memory/iris_profile.md, AGENTS.md, .agents/*.md） |
| 2026-05-13 | `.agent/` を `.agents/` に統合（skillsディレクトリが既に`.agents/`だったため） |
| 2026-05-12 | 1タスク完了ごとにgitコミットを必須とする。コード変更とドキュメント更新は同一コミットに含める |

## 既知の課題・注意点

- Ollama が動作していないと Iris は起動しない（`main.py:_ensure_config_models`）
- ChromaDB の ONNX 埋め込みは初回実行時にモデルを自動DLする（~80MB）
- `memory/data/iris_profile.md` は上限2KBの構造記憶のみ（話し方・性格は `persona_data.json` で動的管理）
- Windows環境を前提としている（パス区切り文字、シェル実行等）

## 最近の作業履歴

| 日付 | 内容 |
|------|------|
| 2026-05-13 | 設計改善リファクタリング: LLMBridge.chat()にmodelパラメータ追加(副作用排除)、ToolExecutionEngine抽出(Executor/cli重複解消)、ConversationService抽出(CliSession神クラス分解)、PersonaProfile SemanticStore非依存化(専用JSON)、VectorStoreスレッドセーフ対応、Config二重パース解消 |
| 2026-05-13 | 自動モデル切替実装: configにfast_model追加、2段階分類(greeting/simple/qa/tool/complex)、context window管理。Qwen3.5:0.5b→Qwen3.5:9bの自動切替 |
| 2026-05-13 | 会話Compaction実装(Step1): core/context.py追加、ConfigManagerによる自動要約(compaction_threshold超過時)、/compactコマンド、conversation_summaryのシステムプロンプト注入 |
| 2026-05-13 | 設計改善refactoring: ConversationService.process_input()を10フェーズに分割、model選択の副作用除去(set_model排除)、RAG二重実行解消、記憶ストアProtocol導入、cli.pyデッドコード削除(_ensure_ollama)、CommandContext型改善、プロンプトプレースホルダ統一 |
