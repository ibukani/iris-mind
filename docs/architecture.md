# Iris アーキテクチャ設計書

> **注記**: 本ドキュメントにおける脳科学・神経科学の用語と層分割の対応付けは、AI による文献調査を参考にした設計指針です。厳密な解剖学的・神経科学的正確性を保証するものではありません。

## 1. 全体像

Iris は脳科学・神経科学の構造を参考にした層分割アーキテクチャを採用する。

```mermaid
flowchart TD
    subgraph Kernel["kernel/ 脳幹+視床下部"]
        K_Manager["KernelManager<br/>プロセス管理・状態集約"]
        K_Command["CommandHandler<br/>外部コマンド"]
        K_Supervisor["Supervisor<br/>シグナル管理"]
        K_Factory["Factory<br/>DIコンテナ"]
    end

    subgraph IO["io/ 視床"]
        IO_Manager["IOManager<br/>入出力中継"]
        IO_Trans["transport/<br/>GrpcListener"]
        IO_Session["session/<br/>SessionManager"]
        IO_Auth["auth/<br/>Authenticator"]
    end

    subgraph Limbic["limbic/ 大脳辺縁系"]
        L_Manager["LimbicManager<br/>感情状態管理"]
        L_Amygdala["扁桃体<br/>感情評価"]
        L_ACC["前帯状皮質<br/>感情制御"]
        L_EM["感情記憶<br/>感情タグ付け"]
        L_BF["BigFive<br/>性格特性"]
    end

    subgraph Memory["memory/ 感覚野+海馬+皮質"]
        M_Manager["MemoryManager<br/>記憶オーケストレーション"]
        M_Sensory["sensory/<br/>入力バッファリング"]
        M_Episodic["episodic/<br/>エピソード記憶"]
        M_Semantic["semantic/<br/>意味記憶"]
        M_Hippocampal["hippocampal/<br/>Reflexion"]
        M_Vector["vector/<br/>埋め込み検索"]
        M_Personality["personality/<br/>話し方・自己状態"]
    end

    subgraph Agency["agency/ 前頭前野+大脳基底核+運動野"]
        A_Bus["bus/ 内部EventBus"]

        subgraph Planning["planning/ 前頭前野"]
            P_Manager["PlanningManager<br/>意思決定"]
            P_Scoring["ProactiveScoring<br/>PFCスコアリング"]
        end

        subgraph Execution["execution/ 基底核+運動野"]
            INH["InhibitionController<br/>基底核抑制"]
            E_Manager["ExecutionManager<br/>行動実行"]
            E_LLM["LLMPipeline<br/>LLM呼出+ツールループ"]
        end
    end

    subgraph Infra["LLM / Tools / ContextWindow"]
        I_LLM["llm/"]
        I_CW["LLMContextWindowManager<br/>会話履歴圧縮"]
        I_TOOLS["tools/"]
    end

    subgraph Event["event/ 神経路"]
        EB["Global EventBus"]
    end

    EB ---|全層を結合| Kernel
    EB --- IO
    EB --- Limbic
    EB --- Memory
    EB --- Agency
    EB --- Infra

    A_Bus --- Planning
    A_Bus --- Execution

    Limbic -.->|感情タグ| Memory
    Limbic -.->|ムード変調| Agency
    Memory -.->|性格×感情| Limbic
```

## 2. 層間イベントフロー（基本ループ）

```mermaid
sequenceDiagram
    participant TCP as 外部Client
    participant IO as IO層
    participant EB as Global EventBus
    participant MEM as Memory層
    participant AG as Agency層
    participant KRN as Kernel層

    TCP->>IO: Message (direction:request, target_role:mind)
    IO->>EB: MessageEvent(...)
    EB->>MEM: MessageEvent (MemoryManager購読)
    MEM->>MEM: sensory buffer → flush
    MEM->>EB: InputReady(content)
    EB->>AG: InputReady (PlanningManager直購読)
    AG->>AG: _build_plan → PlanDecided
    AG->>AG: _execute_general(plan)
    AG->>EB: MessageEvent(...)
    EB->>IO: MessageEvent
    IO->>TCP: Message (direction:response)
    AG->>AG: 実行後: reflexion / compression

    KRN->>EB: TimerTick (5秒間隔)
    EB->>MEM: TimerTick (subscribe)
    MEM->>MEM: rate-limit check
    MEM->>EB: InputReady(from_timer=True)
    EB->>AG: InputReady
    AG->>AG: scoring + threshold + gate → PlanDecided
```

## 3. ディレクトリ構成

```
iris/
├── __init__.py
│
├── kernel/                    # 脳幹: プロセス管理 + DI + コマンド
│   ├── __init__.py
│   ├── manager.py             KernelManager（lifecycle, health, state）
│   ├── process.py             KernelProcess（起動・停止, TimerTick発行）
│   ├── supervisor.py          Supervisor（シグナル・コンソール）
│   ├── factory.py             DIコンテナ（全層の構築）
│   └── commands/
│       ├── __init__.py
│       └── handler.py         CommandHandler（/shutdown, /status ...）
│
├── io/                        # 視床: 入出力中継
│   ├── __init__.py
│   ├── manager.py             IOManager
│   ├── models.py              InputMessage, OutputMessage ...
│   ├── transport/
│   │   ├── __init__.py
│   │   ├── iris_service.proto     gRPC Proto定義 (proto/iris/io/)
│   │   ├── grpc_service_pb2.py    自動生成Protobuf
│   │   ├── grpc_service_pb2_grpc.py 自動生成gRPCスタブ
│   │   └── grpc_server.py        GrpcListener / GrpcServer
│   ├── session/
│   │   ├── __init__.py
│   │   └── manager.py         SessionManager
│   └── auth/
│       ├── __init__.py
│       └── authenticator.py   Authenticator
│
├── event/                     # 神経路: グローバルEventBus
│   ├── __init__.py
│   ├── bus.py                 EventBus
│   └── event_types.py         イベント型定義
│
├── limbic/                    # 大脳辺縁系: 感情処理 + 性格特性
│   ├── __init__.py
│   ├── manager.py             LimbicManager（感情状態管理, EventBus連携）
│   ├── models.py              EmotionState（PAD 3次元モデル）
│   ├── amygdala.py            扁桃体（感情評価・価値判断）
│   ├── acc.py                 前帯状皮質（感情制御・葛藤調整）
│   ├── emotional_memory.py    扁桃体-海馬相互作用（感情タグ付け）
│   └── big_five.py            BigFiveProfile + 性格進化
│
├── memory/                    # 記憶系: 感覚野 + 海馬 + 皮質（3層構造）
│   ├── __init__.py
│   ├── manager.py             MemoryManager（EventBus連携, TimerTick rate-limit, ディスパッチャ）
│   ├── sensory/               # 感覚記憶: 生入力の一時保持
│   │   ├── __init__.py
│   │   ├── manager.py         SensoryMemoryManager（断片入力 + raw入力 2系統）
│   │   └── readiness.py       ReadinessEvaluator
│   ├── short_term/            # 短期記憶（ワーキングメモリ）
│   │   ├── __init__.py
│   │   └── manager.py         ShortTermMemoryManager（ターン管理, 検索, エンティティ抽出）
│   ├── long_term/             # 長期記憶: エピソード記憶 + 意味記憶
│   │   ├── __init__.py
│   │   ├── manager.py         LongTermMemoryManager（統合IF）
│   │   ├── stores.py          EpisodicStore + SemanticStore
│   │   └── vector_store.py    VectorStore（ChromaDB + BM25 ハイブリッド）
│   ├── hippocampal/           # 海馬: 記憶整理
│   │   ├── __init__.py
│   │   ├── manager.py         HippocampalManager（Reflexionスケジューリング）
│   │   └── reflexion.py       Reflexion（自己反省, 特性抽出）
    │   └── personality/           # 人格: 話し方・自己状態（記憶から形成）
    │       ├── __init__.py
    │       ├── personality.py     Personality（システムプロンプト構築）
    │       ├── persona_data.py    PersonaData（動的管理）
    │       └── persona_profile.py PersonaProfile（話し方・自己状態）
│
├── agency/                    # 高度認知: PFC + 基底核 + 運動野
│   ├── __init__.py
│   ├── manager.py             AgencyManager（compact_contextの中継のみ）
│   ├── bus.py                 Internal EventBus
│   ├── planning/
│   │   ├── __init__.py
│   │   ├── manager.py         PlanningManager（意思決定, InputReady購読）
│   │   └── scoring.py         ProactiveScoring（PFCスコアリング）
│   └── execution/
│       ├── __init__.py
│       ├── manager.py         ExecutionManager（行動実行, _execute_general統一）
│       ├── pipeline.py        LLMPipeline（generate + ツールループ）
│       ├── inhibition.py      InhibitionController（基底核抑制, GateVerdict）
│       ├── monitor.py         OutputMonitor（発話頻度監視）
│       ├── tool_executor.py   ToolExecutionEngine
│       └── interrupt_token.py InterruptToken
│
├── llm/                       # LLM 基盤
│   ├── __init__.py
│   ├── llm_bridge.py          LLMBridge（マルチプロバイダルーター）
│   ├── provider.py            LLMProvider / ProviderFactory Protocol
│   ├── ollama_provider.py     Ollamaプロバイダ
│   ├── openrouter_provider.py OpenRouterプロバイダ
│   ├── google_provider.py     Googleプロバイダ
│   ├── capability_checker.py
│   ├── tokenizer_manager.py   TokenizerManager（tokenizersラッパー）
│   └── context_window.py      LLMContextWindowManager（会話履歴圧縮）
│
└── tools/                     # @tool, ToolRegistry, ビルトイン
    ├── __init__.py
    ├── decorator.py
    ├── models.py
    ├── registry.py
    └── builtins/              # ツール実装
        ├── file_ops/
        ├── code_exec/
        ├── output/
        └── self_mod/
```

## 4. グローバル EventBus 定義

```python
# iris/event/event_types.py

@dataclass
class MessageEvent:
    session_id: str
    source_role: str
    target_role: str
    direction: str           # "request" | "response" | "stream" | "event"
    msg_type: str            # "chat" | "system" | "stream" | "response" | ...
    content: str
    state: str | None
    correlation_id: str | None
    is_final: bool

@dataclass
class InputReady:
    timestamp: float | None
    source: str
    session_id: str
    content: str
    context: dict | None

@dataclass
class ClientSessionEvent(Event):
    session_id: str
    action: str              # "connected" | "disconnected"
    role: str
    identity: str
    offline_duration: str    # 切断されていた期間（例: "3時間20分間"）

@dataclass
class TimerTick:
    timestamp: float
```

## 5. 状態管理（統合）

`KernelManager` が全体状態を集約する。各層の Manager は自己状態を `StateChange` イベントで Kernel に通知する。

```mermaid
flowchart LR
    subgraph L["状態管理"]
        KS["KernelManager<br/>(全体状態)"]
        MS["MemoryManager<br/>(記憶状態)"]
        AS["AgencyManager<br/>(実行状態)"]
        IS["IOManager<br/>(接続状態)"]
    end

    MS -->|StateChange| KS
    AS -->|StateChange| KS
    IS -->|StateChange| KS
```

状態の種類と責任層:

| 状態 | 管理層 | 説明 |
|------|--------|------|
| `IDLE` | Kernel | システム全体が待機中 |
| `SENSING` | Memory | 入力をバッファリング中 |
| `DECIDING` | Agency/Planning | 意思決定中 |
| `EXECUTING` | Agency/Execution | LLM/Tool 実行中 |
| `CONSOLIDATING` | Memory/Hippocampal | 記憶整理中 |
| `INTERRUPTED` | Agency | 中断中 |
| `SLEEPING` | Kernel | 省電力モード |

## 6. 層間依存ルール

```mermaid
flowchart LR
    Kernel --> Event
    Kernel --> IO
    Limbic --> Event
    Limbic --> Memory
    Limbic --> Agency
    Agency --> Event
    Agency --> Memory
    Agency --> LLM
    Memory --> Event
    IO --> Event
    LLM --> Event
    Event -.->|Notification| All

    subgraph All["全層"]
        IO
        Limbic
        Memory
        Agency
        Kernel
    end
```

- 各層は直接の依存を持たず、EventBus を介して通信する
- ただし Factory（DI コンテナ）は全層のインスタンスを生成するため、kernel/factory.py に集約
- Agency の planning → execution は内部 EventBus を介する
- IO 層は gRPC への依存を持つが、`io/transport/` に閉じる
- Limbic 層は以下のインターフェースで他層と統合する:
  - `build_mood_description()` → LLMPipeline がシステムプロンプトに注入
  - `apply_limbic_modulation(emotion)` → InhibitionController が感情による抑制変調に利用 (inhibition.py)
  - `tag_recent_memory()` → EmotionalMemory が EpisodicStore に感情タグを付与
  - `current_emotion()` → ProactiveScoring が自発発話スコアリングの mood 因子として利用
