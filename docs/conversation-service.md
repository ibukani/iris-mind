# ConversationService 設計仕様

## 概要

ConversationService は会話処理パイプラインの要。EventBus 経由で `UserInputEvent` を購読し、
LLM 応答を生成して `AgentResponseEvent` を発行する。

## 責務

1. **UserInputEvent 購読** — ユーザー入力を検知し処理を開始
2. **LLM 呼び出し** — Personality でシステムプロンプトを構築し、LLM に送信
3. **AgentResponseEvent 発行** — LLM 応答をイベントとして配信（CLI/API で表示）
4. **会話履歴管理** — メッセージリストの保持・クリア

## 処理フロー

```
UserInputEvent
  ↓
ConversationService._on_user_input()
  ├─ 1. メッセージ履歴に user メッセージを追加
  ├─ 2. Personality.build_system_prompt() でシステムプロンプト構築
  ├─ 3. LLMBridge.chat() で LLM 応答を取得
  ├─ 4. メッセージ履歴に assistant メッセージを追加
  └─ 5. AgentResponseEvent 発行 → AgentKernel/CLI が受信
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
├── __init__(event_bus, memory, llm, personality, config)
│   └── subscribe("UserInputEvent", _on_user_input)
├── _on_user_input(event)
│   ├── self._messages.append({"role": "user", ...})
│   ├── _call_llm() → str
│   ├── self._messages.append({"role": "assistant", ...})
│   └── publish(AgentResponseEvent)
├── _call_llm() → str
│   ├── personality.build_system_prompt()
│   └── llm.chat(messages)
└── clear_history()
```

## 依存関係

```
ConversationService
├── EventBus（UserInputEvent 購読 / AgentResponseEvent 発行）
├── MemoryManager（現在は未使用、将来 Reflexion 結果の保存用）
├── LLMBridge（Ollama 呼び出し）
└── Personality（システムプロンプト構築）
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

上限なしの単純リスト（将来 ContextManager で compaction 対応予定）。
`clear_history()` でリセット可能。
