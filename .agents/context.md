# Iris セッションコンテキスト

このファイルはコーディングエージェントが現在のセッションや過去の決定事項を追跡するために使用します。

## プロジェクト状態

- 最新の安定動作バージョン: v0.2.0（移行完了）
- 開発フェーズ: v0.3.0 設計・文書化
- 現在のブランチ: `feature/3-process-architecture`

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
| 2026-05-14 | モデル設定を柔軟化: ModelEntry.role → roles (list), EscalationConfig削除, base_model/smart_model → get_model(role) に統一。モデル数でシングル/マルチを自動判定 |
| 2026-05-14 | iris/commands/ パッケージ実装完了（CommandHandler: /help, /sleep, /wakeup, /compact, /clear, /status, /reflect） |
| 2026-05-14 | pyproject.toml の core*, memory* 参照削除、ruff ignore paths クリーンアップ |
| 2026-05-14 | KernelFactory導入: CLIAdapterの依存構築責務を iris/kernel/factory.py に移動。main.py を composition root 化。Adapter は KernelContext を受け取るだけに |
| 2026-05-14 | **v0.3 方針決定: 3-Process分解（Input / Kernel / Output）。IPCはWindows Named Pipes（AF_PIPE）。Phase順は Protocol抽象 → Output分離 → Input分離。Proactive応答追跡はKernel側に移動。Documentation-Firstで進行** |

## v0.3 設計判断の詳細

### アーキテクチャ
- Input / Kernel / Output の3プロセスに分解（PC五大装置アナロジー）
- 各プロセスは独立起動・停止・置換可能
- Kernel のみが状態を持つ。Input / Output は stateless

### IPC
- Windows Named Pipes（`multiprocessing.connection` の `AF_PIPE`）
- 将来 TCP 移行時は `family="AF_INET"` に変更するだけ
- シリアライズは JSON（`ipc.py:_serialize()` / `_deserialize()`）

### 移行 Phase
1. Phase 0: EventBus Protocol 化 + イベントシリアライズ（trace_id 追加）
2. Phase 1: Output Process 分離（最も独立しやすい）
3. Phase 2: Input Process 分離 + Proactive応答追跡のKernel移動
4. Phase 3: Controller プロセス導入（ライフサイクル管理）
5. Phase 4: マルチ入力ソース対応

### Proactive 応答追跡
- `CLIAdapter._check_proactive_response()` を `ProactiveResponseTracker` として Kernel 内に再実装
- これにより Input Process を純粋な stateless に保つ

### デバッグ戦略
- trace_id による全プロセス横断追跡
- ReplayableTransport によるイベント記録・再生
- 単一プロセスモード（フォールバック）の維持

## 既知の課題・注意点

- Ollama が動作していないと Iris は起動しない（`main.py:_check_environment()`、OpenRouter利用時はスキップ）
- ChromaDB の ONNX 埋め込みは初回実行時にモデルを自動DLする（~80MB）
- `.iris/data/iris_profile.md` は上限2KBの構造記憶のみ（話し方・性格は `persona_data.json` で動的管理）
- Windows環境を前提としている（パス区切り文字、シェル実行等）
- OpenRouter利用時は `config.yaml` の `model.api_key` にAPIキーを設定する（`${ENV_VAR}`形式で環境変数参照可能）
- IPC は当面 Named Pipes（Windows専用）。クロスプラットフォーム対応は将来の課題
