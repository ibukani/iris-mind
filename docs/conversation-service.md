# ConversationService 設計仕様

## 概要

ConversationService は会話処理パイプラインの要。`process_input(content, on_complete?)` を
AgentKernel から呼び出され、LLM 応答を生成して SessionManager 経由で送信する。

## 責務

1. **ユーザー入力処理** — メッセージ履歴に追加し LLM パイプラインを起動
2. **LLM 呼び出し** — Personality でシステムプロンプトを構築し、LLM に送信
3. **出力送信** — SessionManager.route_output() でストリーム・応答を同一TCP接続へ
4. **Tool Call 対応** — LLM が生成した tool_calls を ToolExecutionEngine 経由で実行
5. **side_effect 短絡** — 全 tool_call が side_effect の場合、follow-up LLM 呼び出しをスキップ
6. **ContextManager 連携** — トークン数超過時に会話履歴を自動要約
7. **会話履歴管理** — メッセージリストの保持・クリア

## 処理フロー

```
AgentKernel.on_input(InputMessage)
  ↓
ConversationService.process_input(content)
  ├─ 1. メッセージ履歴に user メッセージを追加
  ├─ 2. SessionManager.route_output("", stream, "") 発行（思考開始通知）
  ├─ 3. LLMPipeline.iterate_with_tools(messages, on_token)
  │     ├─ LLMPipeline._build_system_prompt() で system prompt 構築
  │     ├─ LLM 呼び出し（tools 定義付き）
  │     ├─ tool_calls あり → ToolExecutionEngine.execute_all()
  │     │   ├─ side_effect のみ → break（短絡）
  │     │   └─ 通常ツールあり → 結果を追加 → 再度 LLM（最大3回）
  │     └─ テキスト応答を返す
  ├─ 4. メッセージ履歴に assistant メッセージを追加
  ├─ 5. SessionManager.route_output("", stream, "", done=True) 発行（完了通知）
  ├─ 6. SessionManager.route_output("", response, text) 発行
  ├─ 7. ReflexionManager.maybe_run()（Nターンごと）
  └─ 8. ContextManager.check_and_summarize()（トークン超過時）
```

## イベント連携

EventBus は Kernel 内部イベント（TimerTick, StateChange, MemoryUpdate, Anomaly）専用。
ConversationService は EventBus を経由せず、AgentKernel から直接 `process_input()` を呼ばれる。

```
CLI入力
  │
  ▼
InputMessage (TCP) → TcpListener → KernelProcess._on_input()
  │
  ▼
AgentKernel.on_input(msg)
  ├── 状態遷移 (IDLE→PROCESSING)
  ├── エピソード記憶に記録
  └── ConversationService.process_input(content)
        │
        ├── LLM 呼び出し + Tool 実行
        └── SessionManager.route_output(session_id, OutputMessage) → 同一TCP接続
```

## クラス構成

```
ConversationService
├── __init__(session_manager, llm_pipeline, reflexion_manager?,
│             context_manager?, context_window?)
├── process_input(content, on_complete?)
│   ├── コマンド（/ で始まる）→ CommandHandler のためスキップ
│   ├── self._messages.append({"role": "user", ...})
│   ├── SessionManager.route_output("", stream, "")
│   ├── LLMPipeline.iterate_with_tools(messages, on_token) → str
│   │   └── on_token → SessionManager.route_output("", stream, delta)
│   ├── self._messages.append({"role": "assistant", ...})
│   ├── SessionManager.route_output("", stream, "", done=True)
│   ├── SessionManager.route_output("", response, text)
│   ├── ReflexionManager.maybe_run()
│   └── ContextManager.check_and_summarize()
├── session_reflect() → セッション終了時の完全反省
├── force_compact() → 強制要約
├── clear_history() → 会話履歴クリア
└── _messages: list[dict] — メッセージ履歴
```

## 依存関係

```
ConversationService
├── SessionManager（OutputMessage ルーティング）
├── LLMPipeline（システムプロンプト構築 + LLM呼び出し + ツールループ）
├── ReflexionManager（Nターンごとの quick_reflect、オプション）
└── ContextManager（会話履歴 compaction、オプション）
```

## 会話履歴

`self._messages: list[dict]` に全メッセージを保持:
```python
[
    {"role": "user", "content": "hello"},
    {"role": "assistant", "content": "Hi there!"},
    ...
]
```

LLM にはシステムプロンプトを先頭に追加して送信:
```python
messages = [
    {"role": "system", "content": system_prompt},
    *self._messages,
]
```

デフォルトでは無制限だが、`ContextManager` を設定するとトークン数が `context_window × compaction_threshold` を超えた時点で要約が実行される。
要約後は古いメッセージが system メッセージ（`## Session Summary`）に置き換わる。
`clear_history()` でリセット可能。
