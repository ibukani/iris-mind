# Iris セッションコンテキスト

このファイルはコーディングエージェントが現在のセッションや過去の決定事項を追跡するために使用します。

## プロジェクト状態

- 最新の安定動作バージョン: v0.2.0（移行完了）
- 開発フェーズ: 安定化・機能拡充
- 現在のブランチ: `feature/arch-refactor`

## 重要な決定事項

| 日付 | 決定内容 |
|------|----------|
| 2026-05-12 | 機能変更時はドキュメント更新を必須とする（docs/*.md, .iris/data/iris_profile.md, AGENTS.md, .agents/*.md） |
| 2026-05-13 | `.agent/` を `.agents/` に統合（skillsディレクトリが既に`.agents/`だったため） |
| 2026-05-12 | 1タスク完了ごとにgitコミットを必須とする。コード変更とドキュメント更新は同一コミットに含める |
| 2026-05-13 | アーキテクチャをヘキサゴナル + イベント駆動に刷新。`core/` → `iris/` へ移行 |
| 2026-05-13 | ガバナンスモデルを3層（Tier1自動/Tier2自己判断/Tier3AgentKernel介入）に決定 |
| 2026-05-13 | EventBusはインメモリ同期型で進行。将来分散対応可能にインターフェースを分離 |
| 2026-05-14 | adapters/ を iris/ からルートに移動（依存方向の物理強制） |
| 2026-05-14 | Reflexion 組み込み（会話Nターンごとに自動学習） |
| 2026-05-14 | ContextManager 移植（会話履歴 compaction） |
| 2026-05-14 | core/ 完全削除 + capabilities/iris/memory → iris/ に完全移植 |
| 2026-05-14 | OpenRouter対応: Provider Protocol導入、OllamaProvider/OllamaProvider抽出、OpenRouterProvider新規実装 |

## 既知の課題・注意点

- Ollama が動作していないと Iris は起動しない（`main.py:_ensure_config_models`、OpenRouter利用時はスキップ）
- ChromaDB の ONNX 埋め込みは初回実行時にモデルを自動DLする（~80MB）
- `.iris/data/iris_profile.md` は上限2KBの構造記憶のみ（話し方・性格は `persona_data.json` で動的管理）
- Windows環境を前提としている（パス区切り文字、シェル実行等）
- OpenRouter利用時は `config.yaml` の `model.api_key` にAPIキーを設定する（`${ENV_VAR}`形式で環境変数参照可能）
