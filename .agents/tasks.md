# Iris タスク管理

このファイルはコーディングエージェントが進行中のタスクを追跡するために使用します。

## タスク一覧

| 状態 | 優先度 | タスク | 備考 |
|------|--------|--------|------|
| completed | high | 設計改善リファクタリング2: ConversationService分割・モデル選択副作用除去・RAG二重実行解消・記憶ストアProtocol導入・cli.pyデッドコード削除・CommandContext型改善・プロンプト統一 | ドキュメント更新含む |
| completed | high | KernelFactory導入: CLIAdapterの依存構築責務を kernel/factory.py に移動。main.py を composition root 化 | ドキュメント更新含む |

## 凡例

- `状態`: pending / in_progress / completed / cancelled / blocked
- `優先度`: high / medium / low

## 活用ルール

- タスク着手時に新しい行を追加する
- 完了時に対応する行を完了状態に更新する
- このタスク管理はコーディングエージェントと人間の両方が参照する
