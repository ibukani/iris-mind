# Iris アーキテクチャ設計書 — Kernel-only

## 1. 全体像

このリポジトリは Iris Kernel 本体のみを提供する。UI 層（CLI 等）は別プロジェクトが担当する。
Kernel は Supervisor (main.py) により管理され、Named Pipe で外部プロセスからの制御を受け付ける。

```
┌──────────────────────────────────────────────┐
│              Supervisor (main.py)              │
│  管理コンソール (stdin)  Ctrl+C                │
│       │                                       │
│       ▼                                       │
│  Kernel Process (iris/kernel/)                 │
│  ├── EventBus, AgentKernel, Conversation       │
│  ├── Proactive, Memory, LLM, Tools             │
│  ├── ControlManager (Listener) ← 認証制御      │
│  ├── InputManager (Listener) ← 入力メッセージ  │
│  └── OutputManager (Listener) → 出力メッセージ │
└──────────────────────────────────────────────┘
```

Kernel は ControlManager/InputManager/OutputManager 共に Listener（サーバー）として起動し、
外部 Client の接続を待つ。認証は Control Pipe で事前に行い、Input/Output Pipe は
セッション確立後に使用される。UI 層（CLI 等）はこのリポジトリの管轄外とし、
Named Pipe を介して別プロジェクトから接続する。

## 2. レイヤードアーキテクチャ（v0.2 からの継承）

### 依存方向

```
debug_tools/ ──→ iris/kernel/ ──→ iris/llm/, iris/memory/, iris/capabilities/
(デバッグ用)    (ドメイン層)        (インフラ層)
```

- v0.2 のヘキサゴナルアーキテクチャを継承
- `iris/kernel/` はドメイン層として変化しない
- Kernel は Named Pipe で公開インターフェースを提供するが、UI層はこのリポジトリの管轄外

### コンポーネントマップ（Kernel Process 内部）

```
Kernel Process
├── EventBus (Protocol)       — 内部イベントルーティング（TimerTick, StateChange...）
│   └── EventBus (in-memory)  — 単一プロセス同期型イベントバス
├── I/O Manager
│   ├── ControlManager        — Named Pipe 待受（認証ハンドシェイク）
│   ├── SessionManager        — セッション管理（認証、ペアリング、ルーティング）
│   ├── Authenticator         — 認証ロジック
│   ├── InputManager          — Named Pipe 待受（入力メッセージ処理）
│   └── OutputManager         — Named Pipe 待受（出力メッセージ送信）
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
class ConnectionMode(Enum):
    INPUT_ONLY = "input_only"
    OUTPUT_ONLY = "output_only"
    BIDIRECTIONAL = "bidirectional"

class SessionState(Enum):
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    WAITING_INPUT = "waiting_input"
    WAITING_OUTPUT = "waiting_output"
    ACTIVE = "active"
    CLOSED = "closed"

class AuthMessage(BaseModel):
    msg_type: str = "auth"
    session_id: str
    auth_token: str | None = None
    mode: ConnectionMode = ConnectionMode.BIDIRECTIONAL

class ControlMessage(BaseModel):
    msg_type: str  # "auth_success", "auth_failure", "error"
    session_id: str | None = None
    error_message: str | None = None

class InputMessage(BaseModel):
    id: str           # uuid4 hex (12桁)
    session_id: str   # セッション識別子
    source: str       # "cli", "tcp", ...
    msg_type: str     # "text", "command", ...
    content: str      # メッセージ本文
    content_type: str # "text/plain" (default)
    metadata: dict    # 拡張用

class OutputMessage(BaseModel):
    id: str
    session_id: str   # セッション識別子
    correlation_id: str | None  # 対応する入力のID
    msg_type: str     # "response", "stream", "proactive", "anomaly", ...
    content: str      # メッセージ本文
    content_type: str # "text/plain", "text/markdown", ...
    destinations: list[str] | None  # 出力先フィルタ
    metadata: dict

class SessionInfo(BaseModel):
    session_id: str
    state: SessionState
    mode: ConnectionMode
    control_conn: Any | None
    input_conn: Any | None
    output_conn: Any | None
    created_at: datetime
    last_activity: datetime
```

**データフロー:**

```
外部 Client → Control Pipe → 認証ハンドシェイク (AuthMessage)
                              ↓
                      SessionManager.authenticate()
                              ↓
                     ControlMessage (auth_success)
                              ↓
外部 Client → Input Pipe → InputMessage (session_id 付き) → InputManager._serve()
                              ↓
                       AgentKernel.on_input()
                              ↓
                  ConversationService.process_input()
                              ↓
                    OutputManager.send(OutputMessage(...))
                              ↓
                         Output Pipe → 外部 Client
```

### 認証・セッション管理フロー

```
[接続確立]
外部 Client:
  Control Pipe に接続 (\\.\pipe\iris-kernel-control)
  → AuthMessage(session_id="xxx", mode="bidirectional", auth_token="...")
    ────────── Control Pipe ──────────
Kernel Process:
  ControlManager._serve(): 受信 → SessionManager.on_control_connect()
    → Authenticator.authenticate()  # session_id 検証
    → ControlMessage(msg_type="auth_success") 返信
    ────────── Control Pipe ──────────
外部 Client:
  Input Pipe に接続 (\\.\pipe\iris-kernel-input)
  → InputMessage(session_id="xxx", ...) 送信
    ────────── Input Pipe ──────────
Kernel Process:
  InputManager._serve(): 受信 → SessionManager.on_input_connect(session_id, conn)
    → セッション状態を WAITING_INPUT → WAITING_OUTPUT (or ACTIVE if OUTPUT_ONLY)
外部 Client:
  Output Pipe に接続 (\\.\pipe\iris-kernel-output)
  → session_id を送信
    ────────── Output Pipe ──────────
Kernel Process:
  OutputManager._accept_loop(): 受信 → SessionManager.on_output_connect(session_id, conn)
    → セッション状態を ACTIVE に更新
    → 以降、Input/Output 双方向通信可能
```

### イベントフロー例

```
[ユーザー入力]
外部 Client (例: CLI):
  input() → InputMessage(session_id="xxx", source="cli", content="...")
    ────────── Pipe (\\.\pipe\iris-kernel-input) ──────────
Kernel Process:
  InputManager._serve(): conn.recv_bytes() → json.loads → InputMessage
    → session_id のセッションが ACTIVE か確認
    → AgentKernel.on_input(msg)                     # 状態遷移 + 記憶
    → ConversationService.process_input(msg)         # LLM処理
      → OutputManager.send(OutputMessage(session_id="xxx", msg_type="stream", content="..."))  # 逐次
      → OutputManager.send(OutputMessage(session_id="xxx", msg_type="response", content="...")) # 最終
    → ProactiveEngine.notify_user_activity()         # 抑制更新
    ────────── Pipe (\\.\pipe\iris-kernel-output) ──────────
外部 Client (例: CLI):
  conn.recv_bytes() → OutputMessage → 表示処理
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
│   │   │   ├── models.py        # InputMessage / OutputMessage / AuthMessage / SessionInfo
│   │   │   ├── authenticator.py # 認証ロジック
│   │   │   ├── session_manager.py # セッション管理
│   │   │   ├── control_manager.py # 制御パイプ管理
│   │   │   ├── input_manager.py # 入力メッセージ処理
│   │   │   └── output_manager.py# 出力メッセージ送信
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
│   ├── architecture.md           # 本書
│   ├── ipc-spec.md               # IPC プロトコル仕様
│   └── ... (既存の各設計書)
├── main.py
└── config.yaml
```
