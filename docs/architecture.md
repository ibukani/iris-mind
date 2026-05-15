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
│  │  (CLI, TCP...)  │   \\.\pipe\      │  (EventBus,      │  │
│  │                 │   iris-kernel   │   AgentKernel,   │  │
│  └─────────────────┘                 │   Conversation,  │  │
│                                      │   Proactive,     │  │
│  ┌─────────────────┐                 │   Memory, LLM,   │  │
│  │  Output Process │◄──────────────►│   Tools)          │  │
│  │  (CLI)          │   \\.\pipe\      └─────────────────┘  │
│  │                 │   iris-kernel                       │
│  └─────────────────┘                                      │
└───────────────────────────────────────────────────────────┘
```

各プロセスは独立して起動・停止・置換可能。
Kernel が中心的な状態を持ち、Input / Output は stateless に保つ。

## 2. レイヤードアーキテクチャ（v0.2 からの継承）

### 依存方向

```
adapters/cli/ ──→ iris/kernel/ ──→ iris/llm/, iris/memory/, iris/capabilities/
(UI層)           (ドメイン層)        (インフラ層)
```

- v0.2 のヘキサゴナルアーキテクチャを継承
- v0.3 では `adapters/cli/` が Input / Output の2プロセスに分離される
- `iris/kernel/` はドメイン層として変化しない

### コンポーネントマップ（Kernel Process 内部）

```
Kernel Process
├── EventBus (Protocol)       — 内部イベントルーティング（TimerTick, StateChange...）
│   └── EventBus (in-memory)  — 単一プロセス同期型イベントバス
├── I/O Manager
│   ├── InputManager          — Named Pipe 待受（multiprocessing.connection.Listener）
│   └── OutputManager         — Output Process への送信（Client）
├── KernelProcess             — プロセス起動・監視・ライフサイクル管理
│   └── AgentKernel           — 状態管理・異常検知・イベント統括
├── ConversationService       — 会話オーケストレーション
│   ├── LLMPipeline           — LLM呼び出し＋ツールループ（side_effect 短絡対応）
│   └── ReflexionManager      — 自己反省スケジューリング
├── ProactiveEngine           — 自発発話＋3層ガバナンス
├── MemoryManager             — 記憶操作の一元管理
├── ToolExecutionEngine       — Tool Call実行（side_effect 考慮）
├── CapabilityRegistry        — ツール管理（@tool デコレータ + ToolRegistry 統合）
├── CommandHandler            — スラッシュコマンド処理
└── ContextManager            — 会話履歴 compaction
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

内部イベント（EventBus 経由）:

| イベント | 説明 | 送信元 → 送信先 |
|----------|------|----------------|
| `TimerTick` | 定期タイマー | Kernel (内部) |
| `AgentStateChangeEvent` | 状態遷移 | Kernel (内部) |
| `MemoryUpdateEvent` | 記憶更新 | Kernel (内部) |
| `AgentAnomalyEvent` | 異常検知 | Kernel → Output |

### I/O Message モデル

プロセス間通信は Event ではなく Pydantic モデル（`InputMessage` / `OutputMessage`）を使用する。
EventBus は Kernel 内部のイベントルーティングに限定され、プロセス間は Pipe 経由の JSON メッセージでやり取りする。

```python
# iris/kernel/io/models.py
class InputMessage(BaseModel):
    id: str           # uuid4 hex (12桁)
    source: str       # "cli", "tcp", ...
    msg_type: str     # "text", "command", ...
    content: str      # メッセージ本文
    content_type: str # "text/plain" (default)
    metadata: dict    # 拡張用

class OutputMessage(BaseModel):
    id: str
    correlation_id: str | None  # 対応する入力のID
    msg_type: str     # "response", "stream", "proactive", "anomaly", ...
    content: str      # メッセージ本文
    content_type: str # "text/plain", "text/markdown", ...
    destinations: list[str] | None  # 出力先フィルタ
    metadata: dict
```

**データフロー:**

```
Input Process → InputMessage (JSON) → Pipe → InputManager._serve()
                                                    ↓
                                             AgentKernel.on_input()
                                                    ↓
                                         ConversationService.process_input()
                                                    ↓
                                           OutputManager.send(OutputMessage(...))
                                                    ↓
                                               Pipe → Output Process (Renderer)
```

### イベントフロー例

```
[ユーザー入力]
Input Process:
  input(">>> ") → InputManager.send(InputMessage(source="cli", content="..."))
    ────────── Pipe (\\.\pipe\iris-kernel-input) ──────────
Kernel Process:
  InputManager._serve(): conn.recv_bytes() → json.loads → InputMessage
    → AgentKernel.on_input(msg)                     # 状態遷移 + 記憶
    → ConversationService.process_input(msg)         # LLM処理
      → OutputManager.send(OutputMessage(msg_type="stream", content="..."))  # 逐次
      → OutputManager.send(OutputMessage(msg_type="response", content="...")) # 最終
    → ProactiveEngine.notify_user_activity()         # 抑制更新
    ────────── Pipe (\\.\pipe\iris-kernel-output) ──────────
Output Process:
  Renderer.handle(message): msg_type で分岐 → Rich Live 更新
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

## 7. フォルダ構成（v0.3 現在）

```
iris-kernel/
├── .iris/                       # 設定・データファイル
├── adapters/                    # UI層 アダプター
│   ├── __init__.py
│   └── cli/
│       ├── __init__.py
│       ├── input_main.py        # Input Process（send-only）
│       ├── output_main.py       # Output Process（recv-only）
│       └── renderer.py          # OutputMessage ベース表示
├── debug_tools/                 # デバッグ用ツール
│   └── tcp_input/
│       └── main.py              # TCP Input アダプター
├── iris/
│   ├── kernel/                  # Kernel Process（ドメイン層）
│   │   ├── __init__.py
│   │   ├── config.py            # Config, ModelConfig
│   │   ├── agent_state.py       # AgentStateManager
│   │   ├── core/                # コアコンポーネント
│   │   │   ├── agent_kernel.py  # AgentKernel
│   │   │   ├── kernel_process.py# KernelProcess
│   │   │   └── factory.py       # KernelFactory（composition root）
│   │   ├── event/               # 内部イベント
│   │   │   ├── event.py
│   │   │   └── event_bus.py
│   │   ├── io/                  # I/O Manager
│   │   │   ├── __init__.py
│   │   │   ├── models.py        # InputMessage / OutputMessage + Pipe 定数
│   │   │   ├── input_manager.py # Kernel 側 Listener
│   │   │   └── output_manager.py# Kernel 側 Client
│   │   ├── logging.py
│   │   └── services/            # ビジネスロジック
│   │       ├── __init__.py
│   │       ├── context.py       # ContextManager
│   │       ├── conversation.py  # ConversationService
│   │       ├── llm_pipeline.py  # LLMPipeline（side_effect 短絡対応）
│   │       ├── memory_manager.py
│   │       ├── proactive.py     # ProactiveEngine
│   │       ├── reflexion.py
│   │       ├── reflexion_manager.py
│   │       └── tool_executor.py # ToolExecutionEngine（side_effect 対応）
│   ├── llm/
│   ├── memory/
│   ├── capabilities/            # ツール実装（@tool デコレータ + register() 互換）
│   │   ├── __init__.py
│   │   ├── registry.py          # CapabilityRegistry（ToolRegistry 統合）
│   │   ├── code_exec/server.py
│   │   ├── file_ops/server.py
│   │   └── self_mod/server.py
│   ├── tools/                   # 型安全ツール基盤
│   │   ├── __init__.py
│   │   ├── models.py            # ToolDef, ToolResult
│   │   ├── decorator.py         # @tool() デコレータ + スキーマ自動生成
│   │   ├── registry.py          # ToolRegistry
│   │   └── builtins/
│   │       ├── __init__.py
│   │       └── output.py        # output_to（side_effect）
│   ├── commands/
│   └── personality/
├── docs/
│   ├── README.md
│   ├── adr/
│   │   └── 001-3-process-architecture.md
│   ├── architecture.md           # 本書
│   ├── ipc-spec.md               # IPC プロトコル仕様
│   └── ... (既存の各設計書)
├── main.py
└── config.yaml
```
