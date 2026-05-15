# Iris タスク管理

このファイルはコーディングエージェントが進行中のタスクを追跡するために使用します。

## タスク一覧

| 状態 | 優先度 | タスク | 備考 |
|------|--------|--------|------|
| completed | high | 設計改善リファクタリング2: ConversationService分割・モデル選択副作用除去・RAG二重実行解消・記憶ストアProtocol導入・cli.pyデッドコード削除・CommandContext型改善・プロンプト統一 | |
| completed | high | KernelFactory導入: CLIAdapterの依存構築責務を kernel/factory.py に移動。main.py を composition root 化 | |
| completed | high | テスト実装: Protocol+Fake+プロパティベースのテストスイート（179 tests, 9秒） | |
| completed | high | ADR-001: 3-Process分解の設計文書化（docs/adr/001-3-process-architecture.md） | |
| completed | high | IPCプロトコル仕様書作成（docs/ipc-spec.md） | |
| completed | high | 移行ロードマップ作成（docs/migration-roadmap.md） | |
| completed | high | アーキテクチャ設計書更新（docs/architecture.md） | |
| completed | high | EventBus仕様書更新（docs/event-bus.md） | |
| completed | medium | 運用文書更新（.agents/*.md, AGENTS.md, docs/README.md） | |
| completed | high | Phase 0: EventBus Protocol 化 + event.py + ipc.py 実装 | |
| completed | high | Phase 1: Output Process 分離（output_main.py, renderer.py, OutputBridge） | |
| completed | high | Phase 2: Input Process 分離 + ProactiveResponseTracker移植 + CommandRouter | |
| completed | high | Phase 3: Controller プロセス導入（KernelProcess + ヘルスチェック + 自動再起動） | |
| completed | low | Phase 4a: TCP Input アダプター実装（debug_tools/tcp_input/） | |
| completed | high | Phase 10: ipc.py→transport.py リネーム、ipc_input.py/ipc_output.py 削除 | |
| completed | high | Phase 11: テスト修正 + ドキュメント更新 (220 tests) | |
| completed | high | `debug_tools/cli/` → `adapters/cli/` リネーム。`server.py` 削除。`debug_tools/` は `tcp_input/` のみに縮小。 | |
| completed | high | Kernel-only プロジェクト化: `adapters/` 削除、管理コンソール追加、`/shutdown` 対応、`OutputManager` Listener 化 | |
| completed | high | ドキュメント全面更新: kernel-only を明記。古い 3-Process 分解の記述を削除。ADR-001 に追記。 | |
| completed | high | セッション管理機能: 3-Pipe構成(Control/Input/Output)、認証ハンドシェイク、SessionManager、Authenticator、ConnectionMode対応 (247 tests) | |

## 凡例

- `状態`: pending / in_progress / completed / cancelled / blocked
- `優先度`: high / medium / low

## 活用ルール

- タスク着手時に新しい行を追加する
- 完了時に対応する行を完了状態に更新する
- このタスク管理はコーディングエージェントと人間の両方が参照する
