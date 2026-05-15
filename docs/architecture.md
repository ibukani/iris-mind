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
debug_tools/ ──→ iris/kernel/ ──→ iris/llm/, iris/memory/, iris/capabilities/
```

- v0.2 のヘキサゴナルアーキテクチャを継承
- v0.3 では `debug_tools/` が Input / Output の2プロセスに分離される
- `iris/kernel/` はドメイン層として変化しない

### コンポーネントマップ（Kernel Process 内部）

```
Kernel Process
├── EventBus (Protocol)       — イベントルーティング
│   ├── EventBus (in-memory)  — 単一プロセスモード
│   └── ReplayableTransport   — デバッグ用記録・再生（transport.py）
├── I/O Manager
│   ├── InputManager          — Named Pipe 待受（multiprocessing.connection.Listener）
│   ├── OutputManager         — Output Process への送信
│   ├── InputDriver (Protocol)— 入力アダプター（CLI, TCP, file）
│   └── OutputDriver (Protocol)— 出力アダプター（CLI）
├── KernelProcess             — プロセス起動・監視・ライフサイクル管理
├── AgentKernel               — 状態管理・異常検知・イベント統括
├── ConversationService       — 会話オーケストレーション
│   ├── LLMPipeline           — LLM呼び出し＋ツールループ
│   └── ReflexionManager      — 自己反省スケジューリング
├── ProactiveEngine           — 自発発話＋3層ガバナンス（応答評価含む）
├── MemoryManager             — 記憶操作の一元管理
├── ToolExecutionEngine       — Tool Call実行
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
InputDriver  → InputMessage (JSON) → Pipe → InputManager._serve()
                                                   ↓
                                            AgentKernel.on_input()
                                                   ↓
                                        ConversationService.process_input()
                                                   ↓
                                          OutputManager.send(OutputMessage(...))
                                                   ↓
                                              Pipe → OutputDriver.write(message)
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
├── .iris/                       # 設定・データファイル（不変）
├── debug_tools/
│   ├── __init__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── input_main.py        # Input Process
│   │   ├── output_main.py       # Output Process
│   │   ├── renderer.py          # 表示ロジック
│   │   └── server.py            # 単一プロセス互換用
│   └── tcp_input/               # TCP Input アダプター
├── iris/
│   ├── kernel/
│   │   ├── __init__.py
│   │   ├── agent_kernel.py
│   │   ├── agent_state.py
│   │   ├── config.py
│   │   ├── context.py
│   │   ├── kernel_process.py    # プロセス管理（IrisController）
│   │   ├── conversation.py
│   │   ├── event.py             # イベントクラス群
│   │   ├── event_bus.py         # EventBusProtocol + EventBus
│   │   ├── factory.py
│   │   ├── io/                  # I/O Manager（Input/Output管理）
│   │   │   ├── __init__.py
│   │   │   ├── models.py        # InputMessage / OutputMessage
│   │   │   ├── protocols.py     # InputDriver / OutputDriver Protocol
│   │   │   ├── input_manager.py # Named Pipe 待受
│   │   │   └── output_manager.py# Output Pipe 送信
│   │   ├── ipc/                 # IPC トランスポート
│   │   │   ├── __init__.py
│   │   │   └── transport.py     # ReplayableTransport（デバッグ用）
│   │   ├── memory_manager.py
│   │   ├── proactive.py         # ProactiveEngine（応答評価含む）
│   │   ├── reflexion.py
│   │   ├── reflexion_manager.py
│   │   ├── llm_pipeline.py
│   │   ├── logging.py
│   │   └── tool_executor.py
│   ├── llm/
│   ├── memory/
│   ├── capabilities/
│   │   └── io/                  # I/O Driver 実装
│   │       ├── __init__.py
│   │       ├── cli/driver.py
│   │       ├── tcp/driver.py
│   │       └── file/driver.py
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
