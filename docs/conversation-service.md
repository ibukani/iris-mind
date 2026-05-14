# ConversationService 設計仕様

## 概要

ConversationService は会話処理パイプラインの要。EventBus 経由で `UserInputEvent` を購読し、
LLM 応答を生成して `AgentResponseEvent` を発行する。

## 責務

1. **UserInputEvent 購読** — ユーザー入力を検知し処理を開始
2. **LLM 呼び出し** — Personality でシステムプロンプトを構築し、LLM に送信
3. **AgentResponseEvent 発行** — LLM 応答をイベントとして配信（CLI/API で表示）
4. **Tool Call 対応** — LLM が生成した tool_calls を CapabilityRegistry 経由で実行
5. **ContextManager 連携** — トークン数超過時に会話履歴を自動要約
6. **会話履歴管理** — メッセージリストの保持・クリア

## 処理フロー

```
UserInputEvent
  ↓
ConversationService._on_user_input()
  ├─ 1. メッセージ履歴に user メッセージを追加
  ├─ 2. AgentStreamEvent(delta="") 発行（思考開始通知）
  ├─ 3. LLMPipeline.iterate_with_tools(messages, on_token)
  │     ├─ LLMPipeline._build_system_prompt() で system prompt 構築
  │     ├─ LLM 呼び出し（tools 定義付き）
  │     ├─ tool_calls あり → ToolExecutionEngine.execute_all() → 再度 LLM（最大3回）
  │     └─ tool_calls なし → テキスト応答を返す
  ├─ 4. メッセージ履歴に assistant メッセージを追加
  ├─ 5. AgentStreamEvent(delta="", done=True) 発行（完了通知）
  ├─ 6. AgentResponseEvent 発行
  ├─ 7. ReflexionManager.maybe_run()（Nターンごと）
  └─ 8. ContextManager.check_and_summarize()（トークン超過時）
```

## イベント連携

```
CLI入力
  │
  ▼
UserInputEvent ──→ AgentKernel (IDLE→PROCESSING, 記憶記録)
                ──→ ConversationService (LLM呼出)
                        │
                        ▼
                   AgentResponseEvent ──→ AgentKernel (PROCESSING→IDLE)
                                       ──→ CLI (パネル表示)
```

AgentKernel が先に購読しているため、イベント発行時の実行順は:
1. AgentKernel._on_user_input — 状態遷移 (IDLE→PROCESSING)
2. ConversationService._on_user_input — LLM呼出 → AgentResponseEvent
3. AgentKernel._on_agent_response — 状態遷移 (PROCESSING→IDLE)

この順序により、LLM呼び出し中は ProactiveEngine の発話が抑制される。

## クラス構成

```
ConversationService
├── __init__(event_bus, llm_pipeline, reflexion_manager?,
│             context_manager?, context_window?)
│   └── subscribe("UserInputEvent", _on_user_input)
├── _on_user_input(event)
│   ├── コマンド（/ で始まる）→ CommandRouter に委譲のためスキップ
│   ├── self._messages.append({"role": "user", ...})
│   ├── AgentStreamEvent(delta="") 発行
│   ├── LLMPipeline.iterate_with_tools(messages, on_token) → str
│   ├── self._messages.append({"role": "assistant", ...})
│   ├── AgentStreamEvent(delta="", done=True) 発行
│   ├── publish(AgentResponseEvent)
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
├── EventBus（UserInputEvent 購読 / AgentResponseEvent 発行）
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
要約後は古いメッセージが system メッセージ（`## Session Summary`（v0.2 までは `## 会話の経緯`））に置き換わる。
`clear_history()` でリセット可能。
