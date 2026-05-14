# Iris セッションコンテキスト

このファイルはコーディングエージェントが現在のセッションや過去の決定事項を追跡するために使用します。

## プロジェクト状態

- 最新の安定動作バージョン: v0.2.0（移行完了）
- 開発フェーズ: v0.3.0 Phase 0-3 + TCP Input 実装完了
- 現在のブランチ: `main`

## 重要な決定事項

| 日付 | 決定内容 |
|------|----------|
| 2026-05-12 | 機能変更時はドキュメント更新を必須とする |
| 2026-05-12 | 1タスク完了ごとにgitコミットを必須。コード変更とドキュメント更新は同一コミットに含める |
| 2026-05-13 | EventBusはインメモリ同期型。将来分散対応可能にインターフェース分離 |
| 2026-05-14 | OpenRouter対応: Provider Protocol導入、OllamaProvider/OpenRouterProvider 抽出・実装 |
| 2026-05-14 | モデル設定を柔軟化: `get_model(role)` 統一、モデル数でシングル/マルチ自動判定 |
| 2026-05-14 | KernelFactory導入: main.py を composition root 化。Adapter は KernelContext のみ受け取る |
| 2026-05-14 | v0.3: 3-Process分解（Input/Kernel/Output）。IPCはWindows Named Pipes（AF_PIPE） |

## 既知の課題・注意点

- Ollama が動作していないと Iris は起動しない（`main.py:_check_environment()`、OpenRouter利用時はスキップ）
- ChromaDB の ONNX 埋め込みは初回実行時にモデルを自動DLする（~80MB）
- `.iris/data/iris_profile.md` は上限2KBの構造記憶のみ（話し方・性格は `persona_data.json` で動的管理）
- Windows環境を前提としている（パス区切り文字、シェル実行等）
- OpenRouter利用時は `config.yaml` の `model.api_key` にAPIキーを設定する（`${ENV_VAR}`形式で環境変数参照可能）
- IPC は当面 Named Pipes（Windows専用）。クロスプラットフォーム対応は将来の課題
