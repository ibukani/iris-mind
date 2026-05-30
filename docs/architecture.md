# Iris アーキテクチャ設計書

> **注記**: 本ドキュメントにおける脳科学・神経科学の用語と層分割の対応付けは、AI による文献調査を参考にした設計指針です。厳密な解剖学的・神経科学的正確性を保証するものではありません。

## 1. 全体像

Iris は脳科学・神経科学の構造を参考にした層分割アーキテクチャを採用する。

```mermaid
flowchart TD
    subgraph Kernel["kernel/ 脳幹"]
        K_Plugin["PluginManager<br/>プラグイン管理・DI・状態集約"]
        K_Process["KernelProcess<br/>起動・停止・TimerTick"]
        K_Supervisor["Supervisor<br/>シグナル管理"]
        K_Command["CommandHandler<br/>外部コマンド"]
    end

    subgraph IO["io/ 視床"]
        IO_Manager["IOManager<br/>入出力中継"]
        IO_Gateway["Gateway<br/>gRPC Gateway"]
        IO_Handler["Handler<br/>EventBus連携"]
        IO_Trans["transport/<br/>GrpcListener"]
        IO_Session["session/<br/>SessionManager"]
        IO_Auth["auth/<br/>Authenticator"]
    end

    subgraph Memory["memory/ 感覚野+皮質"]
        M_Manager["MemoryManager<br/>記憶オーケストレーション"]
        M_Base["_JsonlStore<br/>基底クラス"]
        M_Sensory["sensory/<br/>入力バッファリング"]
        M_STM["short_term/<br/>ワーキングメモリ"]
        M_LTM["long_term/<br/>エピソード+意味記憶"]
    end

    subgraph Agency["agency/ 前頭前野+基底核+運動野"]
        A_Bus["Internal EventBus<br/>planning↔execution"]

        subgraph Planning["planning/ 前頭前野"]
            P_Manager["PlanningManager<br/>意思決定"]
            P_Judge["ProactiveJudge<br/>判断フロー"]
            P_Scoring["ProactiveScorer<br/>PFCスコアリング"]
        end

        subgraph Inhibition["inhibition/ 基底核"]
            I_Gate["Gate<br/>実行権制御"]
            I_Striatum["Striatum<br/>Plan評価・抑制"]
        end

        subgraph Execution["execution/ 運動野"]
            E_Orch["ExecutionOrchestrator<br/>LangGraph状態マシン"]
            E_LLM["LLMGateway<br/>LLM呼出"]
            E_Engine["ToolEngine<br/>ツール実行"]
        end
    end

    subgraph Limbic["limbic/ 大脳辺縁系"]
        L_Orch["LimbicOrchestrator<br/>Appraisal→Emotion→Relationship"]
        L_App["Appraiser<br/>2段階Appraisal"]
        L_Gen["EmotionGenerator<br/>Plutchik変換"]
        L_Mood["MoodDynamics<br/>時間減衰"]
        L_Rel["RelationshipManager<br/>Bowlby attachment"]
    end

    subgraph Infra["LLM / Tools"]
        I_LLM["llm/<br/>LLMBridge + Tokenizer + Provider"]
        I_TOOLS["tools/<br/>ToolRegistry"]
    end

    subgraph Event["event/ 神経路"]
        EB["Global EventBus"]
    end

    subgraph Account["account/ アカウント管理"]
        ACC_Provider["AccountManager<br/>CRUD・外部ID連携"]
        ACC_Store["AccountStore<br/>JSONL永続化"]
        ACC_Handler["_AccountDispatcher<br/>ControlMessage処理"]
    end

    EB ---|全層を結合| Kernel
    EB --- IO
    EB --- Memory
    EB --- Agency
    EB --- Limbic
    EB --- Infra
    EB --- Account

    A_Bus --- Planning
    A_Bus --- Execution
    Inhibition --- Execution
```

## 2. 層間イベントフロー（基本ループ）

```mermaid
sequenceDiagram
    participant TCP as 外部Client
    participant IO as IO層
    participant EB as Global EventBus
    participant LIM as Limbic層
    participant MEM as Memory層
    participant AG as Agency層
    participant KRN as Kernel層

    TCP->>IO: Message (direction:request, target_role:mind)
    IO->>EB: MessageEvent(...)
    EB->>LIM: MessageEvent (Limbic購読)
    LIM->>LIM: Appraisal→Emotion→Relationship更新
    EB->>MEM: MessageEvent (MemoryManager購読)
    MEM->>MEM: sensory buffer → flush
    MEM->>EB: InputReady(content)
    EB->>AG: InputReady (PlanningManager直購読)
    AG->>AG: _build_plan → PlanDecided
    AG->>AG: _execute_general(plan)
    AG->>EB: MessageEvent(...)
    EB->>IO: MessageEvent
    IO->>TCP: Message (direction:response)

    KRN->>EB: TimerTick (5秒間隔)
    EB->>MEM: TimerTick (subscribe)
    MEM->>MEM: rate-limit check
    MEM->>EB: InputReady(from_timer=True)
    EB->>AG: InputReady
    AG->>AG: scoring + threshold → PlanDecided
```

## 3. ディレクトリ構成

```
iris/
├── __init__.py
│
├── kernel/                    # 脳幹: プロセス管理 + Pluginシステム + コマンド
│   ├── __init__.py
│   ├── manager.py             PluginManager（全Plugin指揮 + DI + 状態集約）
│   ├── process.py             KernelProcess（起動・停止, TimerTick発行）
│   ├── supervisor.py          Supervisor（シグナル管理）
│   ├── config.py              KernelConfig
│   ├── capture_formatter.py   DebugCapture出力整形
│   ├── debug_capture.py       DebugCapture（キャプチャ管理）
│   ├── diagnostics.py         SystemDiagnostics（状態診断）
│   ├── logging.py             Logging設定
│   ├── plugin/                # プラグインシステム
│   │   ├── manifest.py
│   │   ├── protocol.py
│   │   ├── lifecycle.py
│   │   ├── service_container.py
│   │   ├── kernel_state.py
│   │   ├── hook_points.py
│   │   ├── hooks.py
│   │   └── loader.py
│   └── commands/
│       ├── __init__.py
│       ├── handler.py         CommandHandler（/shutdown, /status ...）
│       ├── debug_commands.py  デバッグコマンド
│       ├── info_commands.py   情報表示コマンド
│       ├── memory_commands.py 記憶操作コマンド
│       └── state_utils.py     状態ユーティリティ
│
├── io/                        # 視床: 入出力中継
│   ├── __init__.py
│   ├── manager.py             IOManager
│   ├── models.py              Message, CommandInput, CommandOutput ...
│   ├── hooks.py               Hook登録
│   ├── gateway.py             gRPC Gateway
│   ├── handler.py             IO Handler（EventBus連携）
│   ├── transport/
│   │   ├── __init__.py
│   │   ├── iris_service.proto     gRPC Proto定義
│   │   ├── grpc_service_pb2.py    自動生成Protobuf
│   │   ├── grpc_service_pb2_grpc.py 自動生成gRPCスタブ
│   │   ├── grpc_server.py        GrpcServer
│   │   └── grpc_listener.py      GrpcListener
│   ├── session/
│   │   ├── __init__.py
│   │   ├── manager.py         SessionManager
│   │   ├── config.py          SessionConfig
│   │   └── permissions.py     Permission管理
│   └── auth/
│       ├── __init__.py
│       └── authenticator.py   Authenticator
│
├── event/                     # 神経路: グローバルEventBus
│   ├── __init__.py
│   ├── event_bus.py           EventBus
│   ├── event_types.py         イベント型定義
│   └── tracer.py              EventTracer
│
├── account/                   # アカウント管理: ユーザー識別・外部ID連携
│   ├── __init__.py            AccountPlugin (STORE phase)
│   ├── models.py              Account, SessionBinding
│   ├── store.py               AccountStore（JSONL永続化）
│   ├── manager.py             AccountManager（コアサービス）
│   ├── events.py              AccountCreated/Updated/SessionBound/Unbound
│   ├── dispatcher.py          _AccountDispatcher（ControlMessage処理）
│   └── hooks.py               EventBus Hook登録
│
├── heartbeat/                 # TimerTick heartbeat Plugin
│   ├── __init__.py
│   └── service.py             HeartbeatService
│
├── memory/                    # 記憶系: 感覚野 + 皮質（3層構造）
│   ├── __init__.py
│   ├── manager.py             MemoryManager（EventBus連携, ディスパッチャ）
│   ├── protocol.py            MemoryManagerProtocol
│   ├── handler.py             イベントハンドラ
│   ├── dispatcher.py          store/retrieve/search ディスパッチ
│   ├── builder.py             コンポーネント組立
│   ├── hooks.py               Plugin Hook登録
│   ├── base.py                _JsonlStore 基底
│   ├── models.py              ContentBlock等 共通型定義
│   ├── sensory/               # 感覚記憶: 生入力の一時保持
│   │   ├── __init__.py
│   │   ├── manager.py         SensoryMemoryManager（断片入力 + raw入力 2系統）
│   │   └── readiness.py       ReadinessEvaluator
│   ├── short_term/            # 短期記憶（ワーキングメモリ）
│   │   ├── __init__.py
│   │   ├── manager.py         ShortTermMemoryManager
│   │   ├── models.py          TurnData, SearchResult
│   │   ├── scorer.py          重要度スコアリング
│   │   ├── extractor.py       エンティティ抽出
│   │   └── renderer.py        コンテキストレンダリング
│   └── long_term/             # 長期記憶
│       ├── __init__.py
│       ├── manager.py         LongTermMemoryManager
│       ├── stores.py          EpisodicStore + SemanticStore + AgentsMdStore
│       ├── protocols.py       Store プロトコル定義
│       ├── goal_store.py      GoalStore（長期目標管理）
│       └── vector_store.py    VectorStore（ChromaDB + BM25 ハイブリッド）
│
├── agency/                    # 高度認知: PFC + 基底核 + 運動野
│   ├── __init__.py
│   ├── task_level.py           TaskLevel定義 + resolve_level()
│   ├── manager.py             AgencyManager
│   ├── internal_bus.py        Internal EventBus（planning→execution）
│   ├── builder.py             コンポーネント組み立て
│   ├── hooks.py               Plugin Hook登録
│   ├── modulation.py          Agency変調（感情→意思決定への影響）
│   ├── inhibition/            # 基底核: 抑制制御（Striatum+Gate）
│   │   ├── __init__.py
│   │   ├── manager.py         InhibitionManager
│   │   ├── handler.py         抑制ハンドラ
│   │   ├── gate.py            Gate（実行権制御）
│   │   ├── striatum.py        Striatum（Plan評価）
│   │   └── models.py          GateDecision
│   ├── planning/              # 前頭前野: 意思決定
│   │   ├── __init__.py
│   │   ├── manager.py         PlanningManager
│   │   ├── models.py          Plan, PlanReason
│   │   ├── handler.py         Planning Handler（EventBus連携）
│   │   ├── context_hint_builder.py  ContextHintBuilder
│   │   ├── question_generator.py    質問生成
│   │   ├── task_content.py          is_task_content
│   │   ├── utils.py                 Utilities
│   │   ├── decisions/         # プロアクティブ判断
│   │   │   ├── __init__.py
│   │   │   ├── judge.py       ProactiveJudge
│   │   │   └── scorer.py      ProactiveScorer
│   │   └── strategies/        # 計画構築ストラテジ
│   │       ├── __init__.py
│   │       ├── response.py    ResponsePlanStrategy
│   │       └── proactive.py   ProactivePlanStrategy
│   └── execution/             # 基底核+運動野: 行動実行
│       ├── __init__.py
│       ├── orchestrator.py         ExecutionOrchestrator（LangGraph）
│       ├── router.py               LLM応答後ルーティング
│       ├── executor.py             FlowExecutor（Plan購読→グラフ起動）
│       ├── models.py               ExecutionState + DynamicState
│       ├── engine.py               ToolEngine
│       ├── builder.py              ノード・グラフ組立
│       ├── node_type.py            ノード種別定義
│       ├── worker.py               バックグラウンドワーカー
│       ├── handler.py              実行イベントハンドラ
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── gateway.py          LLMGateway
│       │   ├── prompt_builder.py   SystemPromptBuilder
│       │   ├── node_prompt_factory.py  ノード別プロンプト
│       │   ├── profile_builder.py      プロファイル構築
│       │   └── capture.py              LLM入出力キャプチャ
│       ├── nodes/                  # LangGraph ノード
│       │   ├── __init__.py
│       │   ├── base.py             BaseLLMNode
│       │   ├── general_chat.py     GeneralChatNode
│       │   ├── general_task.py     GeneralTaskNode
│       │   ├── setup.py            SetupNode
│       │   ├── tool_run.py         ToolRunNode
│       │   └── finalize.py         FinalizeNode
│       └── regulation/
│           └── consolidator.py     Context圧縮
│
├── limbic/                    # 辺縁系: 感情・関係性 (階段整合
│   ├── __init__.py            LimbicPlugin (LAYER/phase=20)
│   ├── models.py              データ型定義
│   ├── appraiser.py           2段階Appraisal (Lazarus)
│   ├── generator.py           Appraisal→Emotion (Plutchik)
│   ├── mood.py                Mood dynamics
│   ├── relationship.py        Bowlby attachment + 3段階関係性
│   ├── state.py               状態統合
│   ├── orchestrator.py        パイプライン統合
│   └── hooks.py               EventBus購読
│
│   ├── llm/                       # LLM 基盤
│   │   ├── __init__.py
│   │   ├── bridge.py              LLMBridge（マルチプロバイダルーター）
│   │   ├── capability.py          CapabilityChecker
│   │   ├── context.py             LLMContextWindowManager
│   │   ├── hooks.py               Plugin Hook登録
│   │   ├── interrupt_token.py     InterruptToken
│   │   ├── model_factory.py       ChatModelファクトリ
│   │   ├── priority_lock.py       PriorityLock
│   │   ├── prompt.py              Personality（システムプロンプト構築）
│   │   ├── repetition.py          繰り返し検出
│   │   ├── token_utils.py         トークン推定ユーティリティ
│   │   ├── tokenizer.py           TokenizerManager
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── base.py            Provider基底
│   │       ├── ollama.py          Ollamaプロバイダ
│   │       └── openai_compatible.py  OpenAI互換プロバイダ
│
├── tools/                     # @tool, ToolRegistry
│   ├── __init__.py
│   ├── decorator.py           @tool デコレータ
│   ├── models.py              ToolDef, ToolCall
│   ├── registry.py            ToolRegistry
│   └── builtins/              組み込みツール
│
└── admin/                     # CLI管理
    ├── __init__.py
    └── __main__.py            CLIエントリポイント
```

## 4. グローバル EventBus 定義

全イベントは `Event` 基底クラスを継承する（`kw_only=True`、`timestamp`/`source`/`trace_id` を持つ）。
イベント型名は自動レジストリ（`_type_registry`）で管理され、`to_dict()` / `from_dict()` でシリアライズ可能。

```python
# iris/event/event_types.py

@dataclass(kw_only=True)
class Event:
    timestamp: datetime | None
    source: str
    trace_id: str = ""
    # _type_registry, to_dict(), from_dict()

@dataclass
class TimerTick(Event):
    tick_count: int = 0

@dataclass
class AgentStateChangeEvent(Event):
    previous_state: str | None
    new_state: str | None

@dataclass
class MemoryUpdateEvent(Event):
    entry_type: str
    content: str

@dataclass
class AgentAnomalyEvent(Event):
    anomaly_type: str
    severity: str
    detail: str

@dataclass
class MessageEvent(Event):
    session_id: str = ""
    source_role: str = ""
    target_role: str = ""
    account_id: str = ""
    room_id: str = ""
    direction: str = ""      # "request" | "response" | "stream" | "event"
    msg_type: str = ""       # "chat" | "system" | "stream" | "response" | ...
    content: str = ""
    state: str | None = None
    correlation_id: str | None = None

@dataclass
class InputReady(Event):
    session_id: str = ""
    content: str = ""
    account_id: str = ""
    room_id: str = ""
    context: dict | None = None

@dataclass
class ClientSessionEvent(Event):
    session_id: str = ""
    action: str = ""         # "connected" | "disconnected"
    role: str = ""
    session_tag: str = ""
    offline_duration: str = ""

@dataclass
class DebugSnapshotEvent(Event):
    category: str = ""
    data: dict | None = None
    trigger: str = ""

@dataclass
class InterruptEvent(Event):
    session_id: str = ""
```

## 5. 状態管理（統合）

`KernelState`（`iris/kernel/plugin/kernel_state.py`）が全体状態を集約する。
各層の Manager は自己状態を `DebugSnapshotEvent` で通知する。SystemDiagnostics が `get_state()` 命名規約で自動発見する。

```mermaid
flowchart LR
    subgraph L["状態管理"]
        KS["KernelState<br/>(全体状態)"]
        MS["MemoryManager<br/>(記憶状態)"]
        AS["AgencyManager<br/>(実行状態)"]
        IS["IOManager<br/>(接続状態)"]
        LS["LimbicOrchestrator<br/>(感情/関係性状態)"]
    end

    MS -->|DebugSnapshotEvent| KS
    AS -->|DebugSnapshotEvent| KS
    IS -->|DebugSnapshotEvent| KS
    LS -->|DebugSnapshotEvent| KS
```

状態の種類と責任層:

| 状態 | 管理層 | 説明 |
|------|--------|------|
| `IDLE` | Kernel | システム全体が待機中 |
| `SENSING` | Memory | 入力をバッファリング中 |
| `DECIDING` | Agency/Planning | 意思決定中 |
| `EXECUTING` | Agency/Execution | LLM/Tool 実行中 |
| `INTERRUPTED` | Agency | 中断中 |
| `SLEEPING` | Kernel | 省電力モード |

## 6. 層間依存ルール

```mermaid
flowchart LR
    Kernel --> Event
    Kernel --> IO
    Agency --> Event
    Agency --> Memory
    Agency --> LLM
    Limbic --> Event
    Memory --> Event
    IO --> Event
    LLM --> Event
    Event -.->|Notification| All

    subgraph All["全層"]
        IO
        Memory
        Agency
        Limbic
        Kernel
    end
```

- 各層は直接の依存を持たず、EventBus を介して通信する
- PluginManager が全層の構築、DI、ライフサイクル管理を行う（`kernel/manager.py`）
- Agency の planning → execution は内部 EventBus を介する
- IO 層は gRPC への依存を持つが、`io/transport/` に閉じる
- 全Pluginの依存は `PluginManifest.dependencies` に宣言、PluginManagerがトポロジカルソートで解決
