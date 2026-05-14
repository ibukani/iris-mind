# Iris アーキテクチャ設計書

## 1. 全体像

Iris v0.3 は**3プロセス分解アーキテクチャ**を採用する。
Input / Kernel / Output の3プロセスが Windows Named Pipes 経由で通信する。

```
┌───────────────────────────────────────────────────────────┐
│                    Controller Process                      │
│          (起動・監視・シャットダウン)                       │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  ┌─────────────────┐   Named Pipe    ┌─────────────────┐  │
│  │  Input Process  │◄──────────────►│  Kernel Process  │  │
│  │  (CLI, API,     │   \\.\pipe\      │  (EventBus,      │  │
│  │   Discord...)   │   iris-kernel   │   AgentKernel,   │  │
│  └─────────────────┘                 │   Conversation,  │  │
│                                      │   Proactive,     │  │
│  ┌─────────────────┐                 │   Memory, LLM,   │  │
│  │  Output Process │◄──────────────►│   Tools)          │  │
│  │  (CLI, GUI,     │   \\.\pipe\      └─────────────────┘  │
│  │   Speech...)    │   iris-kernel                       │
│  └─────────────────┘                                      │
└───────────────────────────────────────────────────────────┘
```

各プロセスは独立して起動・停止・置換可能。
Kernel が中心的な状態を持ち、Input / Output は stateless に保つ。

## 2. レイヤードアーキテクチャ（v0.2 からの継承）

### 依存方向

```
adapters/ ──→ iris/kernel/ ──→ iris/llm/, iris/memory/, iris/capabilities/
```

- v0.2 のヘキサゴナルアーキテクチャを継承
- v0.3 では `adapters/` がさらに Input / Output の2プロセスに分離される
- `iris/kernel/` はドメイン層として変化しない

### コンポーネントマップ（Kernel Process 内部）

```
Kernel Process
├── EventBus (Protocol)       — イベントルーティング
│   ├── EventBus (in-memory)  — 単一プロセスモード
│   ├── PipeServer            — マルチプロセスモード (IPC)
│   └── ReplayableTransport   — デバッグ用記録・再生
├── AgentKernel               — 状態管理・異常検知・イベント統括
├── ConversationService       — 会話オーケストレーション
│   ├── LLMPipeline           — LLM呼び出し＋ツールループ
│   └── ReflexionManager      — 自己反省
├── ProactiveEngine           — 自発発話＋3層ガバナンス
├── ProactiveResponseTracker  — 自発発話へのユーザー反応評価 (新規)
├── MemoryManager             — 記憶操作の一元管理
├── ToolExecutionEngine       — Tool Call実行
└── CommandHandler            — スラッシュコマンド処理
```

## 3. イベント駆動設計

### EventBus Protocol

```python
class EventBusProtocol(Protocol):
    def publish(self, event: Event) -> None: ...
    def subscribe(self, event_type: str, handler: Callable) -> None: ...
    def unsubscribe(self, event_type: str, handler: Callable) -> None: ...
```

### イベント種別

| イベント | 説明 | 送信元 → 送信先 |
|----------|------|----------------|
| `UserInputEvent` | ユーザー入力 | Input → Kernel |
| `ProactiveSpeechEvent` | 自発発話 | Kernel → Output |
| `TimerTick` | 定期タイマー | Kernel (内部) |
| `AgentStateChangeEvent` | 状態遷移 | Kernel (内部) |
| `AgentStreamEvent` | LLMストリーミングトークン | Kernel → Output |
| `AgentResponseEvent` | LLM最終応答 | Kernel → Output |
| `AgentAnomalyEvent` | 異常検知 | Kernel → Output |

### イベントフロー例

```
[ユーザー入力]
Input Process:
  input(">>> ") → PipeClient.send(UserInputEvent)
    ────────── Pipe ──────────
Kernel Process:
  PipeServer.recv() → EventBus.publish(UserInputEvent)
    → ProactiveResponseTracker._on_user_input()  # 応答評価
    → AgentKernel._on_user_input()               # 状態遷移 + 記憶
    → ConversationService._on_user_input()        # LLM処理
      → EventBus.publish(AgentStreamEvent)        # 逐次
      → EventBus.publish(AgentResponseEvent)      # 最終
    → ProactiveEngine.notify_user_activity()      # 抑制更新
    ────────── Pipe ──────────
Output Process:
  PipeClient.recv() → Renderer.on_stream_token()
    → Rich Live 更新
```

## 4. 3層ガバナンス（v0.2 から継承）

| Tier | 方式 | 例 |
|------|------|-----|
| Tier 1 | ルールベース自動許可 | 挨拶・定型確認 |
| Tier 2 | LLM自己判断 | 話題提案・気遣い |
| Tier 3 | AgentKernel介入 | 異常検知・過剰発話抑制 |

詳細は `docs/proactive-engine.md` を参照。

## 5. 状態遷移（v0.2 から継承）

`AgentStateManager` が管理する6状態：
IDLE / PROCESSING / PROACTIVE / REFLECTING / THINKING / SLEEPING

詳細は `docs/agent-state.md` を参照。

## 6. 記憶システム（v0.2 から継承）

| 記憶種別 | 技術 | 上限 |
|----------|------|------|
| EpisodicStore | JSONL | 30エントリ |
| SemanticStore | ChromaDB + BM25 | 100エントリ |
| PersonaProfile | JSON | 動的 |

詳細は `docs/memory-manager.md` を参照。

## 7. フォルダ構成（v0.3 目標）

```
my-iris/
├── .iris/                       # 設定・データファイル（不変）
├── adapters/
│   ├── __init__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── input_main.py        # Input Process (新規)
│   │   ├── output_main.py       # Output Process (新規)
│   │   └── renderer.py          # 表示ロジック (新規)
│   ├── api/                     # 将来: WebSocket/HTTP Input
│   └── gui/                     # 将来: GUI Output
├── iris/
│   ├── kernel/
│   │   ├── __init__.py
│   │   ├── agent_kernel.py
│   │   ├── agent_state.py
│   │   ├── config.py
│   │   ├── context.py
│   │   ├── controller.py        # 新規: プロセス管理
│   │   ├── conversation.py
│   │   ├── event.py             # 新規: イベントクラス群
│   │   ├── event_bus.py         # EventBusProtocol + EventBus
│   │   ├── factory.py
│   │   ├── ipc.py               # 新規: PipeServer / PipeClient
│   │   ├── ipc_output.py        # 新規: OutputBridge
│   │   ├── ipc_input.py         # 新規: InputBridge
│   │   ├── memory_manager.py
│   │   ├── proactive.py
│   │   ├── proactive_response_tracker.py  # 新規
│   │   ├── reflexion.py
│   │   ├── reflexion_manager.py
│   │   └── tool_executor.py
│   ├── llm/
│   ├── memory/
│   ├── capabilities/
│   ├── commands/
│   └── personality/
├── docs/
│   ├── README.md
│   ├── adr/
│   │   └── 001-3-process-architecture.md  # 新規
│   ├── architecture.md           # 本書
│   ├── ipc-spec.md               # 新規
│   ├── migration-roadmap.md      # 新規
│   └── ... (既存の各設計書)
├── main.py
└── config.yaml
```
