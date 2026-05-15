# コマンドシステム仕様

## 概要

`iris/commands/` パッケージはスラッシュコマンド（`/command`）の解釈と実行を担当する。
`ConversationService.process_input()` が `content.startswith("/")` を検出して即座に return し、`CommandHandler` が処理する。通常の会話処理（LLM呼び出し）をバイパスして即座に応答する。

## コンポーネント

### CommandHandler

`iris/commands/handler.py` — コマンドの登録・解釈・実行を一元管理する。

```python
handler = CommandHandler(state, conversation, proactive)
response = handler.handle("/sleep")  # → "おやすみなさい。..."
```

### 対応コマンド一覧

| コマンド | 引数 | 処理内容 |
|----------|------|----------|
| `/help` | なし | 利用可能なコマンド一覧を表示 |
| `/sleep` | なし | AgentState を SLEEPING に遷移（自発発話・入力応答を中断） |
| `/wakeup` | なし | SLEEPING → IDLE に復帰 |
| `/compact` | なし | 会話履歴を強制要約（ContextManager が compaction） |
| `/clear` | なし | 会話履歴を全て消去（`clear_history()`） |
| `/status` | なし | 現在の状態・抑制情報を表示 |
| `/reflect` | なし | セッション反省（Reflexion.reflect）を強制実行 |

## 依存関係

```
ConversationService (command detection) → CommandHandler → iris/kernel/{agent_state, conversation, proactive}
```

- `iris/commands/` は `iris/kernel/` にのみ依存する
- `iris/kernel/` は `iris/commands/` を知らない（依存方向は一方向）

## 拡張方法

1. `iris/commands/handler.py` の `_COMMANDS` dict にコマンド名と説明を追加
2. `CommandHandler` クラスに `_cmd_<name>(self, args: str) -> str` メソッドを追加
3. `handle()` メソッドのディスパッチテーブルに追記
