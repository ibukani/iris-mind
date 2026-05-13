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
  ├─ 2. Personality.build_system_prompt() + ContextManager.build_compact_messages()
  ├─ 3. _call_llm_with_tools()
  │     ├─ LLM 呼び出し（tools 定義付き）
  │     ├─ tool_calls あり → ToolExecutionEngine で実行 → 再度 LLM
  │     └─ tool_calls なし → テキスト応答
  ├─ 4. メッセージ履歴に assistant メッセージを追加
  ├─ 5. AgentResponseEvent 発行 → AgentKernel/CLI が受信
  ├─ 6. Reflexion.quick_reflect()（Nターンごと）
  └─ 7. ContextManager.check_and_summarize()（トークン超過時）
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
├── __init__(event_bus, memory, llm, personality, config,
│             reflexion?, tool_executor?, context_manager?)
│   └── subscribe("UserInputEvent", _on_user_input)
├── _on_user_input(event)
│   ├── self._messages.append({"role": "user", ...})
│   ├── _call_llm_with_tools() → str
│   ├── self._messages.append({"role": "assistant", ...})
│   ├── publish(AgentResponseEvent)
│   ├── _maybe_quick_reflect()
│   └── _maybe_compact()
├── _call_llm_with_tools() → str
│   ├── LLM 呼び出し（tools 付き）
│   ├── tool_calls → execute_all → 再帰（最大3回）
│   └── 最終テキスト応答を返す
├── _call_llm(tools?) → dict
│   ├── personality.build_system_prompt()
│   ├── context_manager.build_compact_messages()（要約時）
│   └── llm.chat(messages, tools)
├── _maybe_quick_reflect() → Reflexion + SemanticStore保存
├── _maybe_compact() → ContextManager + 履歴圧縮
├── session_reflect() → セッション終了時の完全反省
└── clear_history()
```

## 依存関係

```
ConversationService
├── EventBus（UserInputEvent 購読 / AgentResponseEvent 発行）
├── MemoryManager（Reflexion結果の保存）
├── LLMBridge（Ollama 呼び出し）
├── Personality（システムプロンプト構築）
├── Reflexion（自己反省、オプション）
├── ToolExecutionEngine（Tool Call実行、オプション）
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
