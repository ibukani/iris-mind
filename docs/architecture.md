# Iris v2 アーキテクチャ設計書

## 1. 全体像

Iris v2 は脳科学・神経科学の構造を参考にした層分割アーキテクチャを採用する。

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
        IO_Trans["transport/<br/>TcpListener"]
        IO_Session["session/<br/>SessionManager"]
        IO_Auth["auth/<br/>Authenticator"]
    end

    subgraph Memory["memory/ 感覚野+海馬+皮質"]
        M_Manager["MemoryManager<br/>記憶オーケストレーション"]
        M_Sensory["sensory/<br/>入力バッファリング"]
        M_Episodic["episodic/<br/>エピソード記憶"]
        M_Semantic["semantic/<br/>意味記憶"]
        M_Hippocampal["hippocampal/<br/>Reflexion+圧縮"]
        M_Vector["vector/<br/>埋め込み検索"]
    end

    subgraph Agency["agency/ 前頭前野+大脳基底核+運動野"]
        A_Bus["bus/ 内部EventBus"]
        A_Manager["AgencyManager<br/>橋渡し"]

        subgraph Planning["planning/ 前頭前野"]
            P_Manager["PlanningManager<br/>意思決定"]
        end

        subgraph Execution["execution/ 基底核+運動野"]
            E_Manager["ExecutionManager<br/>行動実行"]
            E_LLM["LLMPipeline<br/>LLM呼出+ツールループ"]
        end
    end

    subgraph Event["event/ 神経路"]
        EB["Global EventBus"]
    end

    subgraph Infra["LLM / Tools / Personality"]
        I_LLM["llm/"]
        I_TOOLS["tools/"]
        I_PERS["personality/"]
    end

    EB ---|全層を結合| Kernel
    EB --- IO
    EB --- Memory
    EB --- Agency
    EB --- Infra

    A_Bus --- Planning
    A_Bus --- Execution
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

    TCP->>IO: InputMessage
    IO->>EB: InputReceived(msg)
    EB->>MEM: InputReceived
    MEM->>MEM: sensory buffer
    MEM->>EB: InputReady(content)
    EB->>AG: InputReady
    AG->>AG: planning → execution
    AG->>EB: OutputRequest(output)
    EB->>IO: OutputRequest
    IO->>TCP: OutputMessage
    AG->>EB: Completed(session_id)
    EB->>MEM: Completed
    MEM->>MEM: 海馬: エピソード保存 / 振り返り判断
```

## 3. ディレクトリ構成

```
iris/
├── __init__.py
│
├── kernel/                    # 脳幹: プロセス管理 + DI + コマンド
│   ├── __init__.py
│   ├── manager.py             KernelManager（lifecycle, health, state）
│   ├── process.py             KernelProcess（起動・停止）
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
│   │   └── tcp_listener.py    TcpListener
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
│   └── events.py              イベント型定義
│
├── memory/                    # 記憶系: 感覚野 + 海馬 + 皮質
│   ├── __init__.py
│   ├── manager.py             MemoryManager（EventBus連携 + plugin呼出）
│   ├── sensory/
│   │   ├── __init__.py
│   │   └── buffer.py          InputBuffer（断片的入力保持）
│   ├── episodic/
│   │   ├── __init__.py
│   │   └── store.py           EpisodicStore（JSONL）
│   ├── semantic/
│   │   ├── __init__.py
│   │   └── store.py           SemanticStore（JSONL + ChromaDB）
│   ├── hippocampal/
│   │   ├── __init__.py
│   │   ├── reflexion.py       Reflexion（LLM分析）
│   │   └── compression.py     ContextManager（会話要約）
│   ├── personality/            # 人格: 性格特性・話し方（記憶から形成）
│   │   ├── __init__.py
│   │   ├── personality.py     Personality（システムプロンプト構築）
│   │   ├── persona_data.py    PersonaData（動的管理）
│   │   └── persona_profile.py PersonaProfile（話し方・性格）
│   └── vector/
│       ├── __init__.py
│       └── store.py           VectorStore（ONNX埋め込み）
│
├── agency/                    # 高度認知: PFC + 基底核 + 運動野
│   ├── __init__.py
│   ├── manager.py             AgencyManager（global↔internal橋渡し）
│   ├── bus.py                 Internal EventBus
│   ├── planning/
│   │   ├── __init__.py
│   │   └── manager.py         PlanningManager（意思決定）
│   └── execution/
│       ├── __init__.py
│       ├── manager.py         ExecutionManager（行動実行）
│       └── pipeline.py        LLMPipeline（LLM呼出 + ツールループ）
│
├── llm/                       # LLM インフラ（変更なし）
│   ├── __init__.py
│   ├── llm_bridge.py
│   ├── provider.py
│   ├── ollama_provider.py
│   ├── openrouter_provider.py
│   └── capability_checker.py
│
├── tools/                     # @tool, ToolRegistry, ビルトイン
    │   ├── __init__.py
    │   ├── decorator.py
    │   ├── models.py
    │   ├── registry.py
    │   └── builtins/              # ツール実装
    │       ├── file_ops/
    │       ├── code_exec/
    │       └── self_mod/
    │
    └── commands/                  # 削除（kernel/commands/ に移動）
```

## 4. グローバル EventBus 定義

```python
# iris/event/events.py

@dataclass
class InputReceived:
    message: InputMessage

@dataclass
class InputReady:
    session_id: str
    content: str
    context: dict

@dataclass
class OutputRequest:
    session_id: str
    message: OutputMessage

@dataclass
class OutputSent:
    session_id: str
    message_id: str

@dataclass
class Completed:
    session_id: str
    summary: str

@dataclass
class TimerTick:
    timestamp: datetime

@dataclass
class CommandRequest:
    command: str
    args: str
    session_id: str
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
    Agency --> Event
    Agency --> Memory
    Agency --> LLM
    Memory --> Event
    IO --> Event
    LLM --> Event
    Event -.->|Notification| All

    subgraph All["全層"]
        IO
        Memory
        Agency
        Kernel
    end
```

- 各層は直接の依存を持たず、EventBus を介して通信する
- ただし Factory（DI コンテナ）は全層のインスタンスを生成するため、kernel/factory.py に集約
- Agency の planning → execution は内部 EventBus を介する
- IO 層は TCP への依存を持つが、`io/transport/` に閉じる

## 7. 旧 v0.3 からの変更点一覧

| 項目 | v0.3 | v2 |
|------|------|----|
| kernel/services/ | 13ファイル全て | 解体、各層に分散 |
| kernel/event/ | kernel 内 | iris/event/ に分離 |
| kernel/io/ | kernel 内 | iris/io/ に分離 |
| ConversationService | 中央集権 | planning + execution に分散 |
| ProactiveEngine | 単一サービス | planning + execution に分割予定 |
| Reflexion | kernel/services/ | memory/hippocampal/ |
| ContextManager | kernel/services/ | memory/hippocampal/ |
| InputBuffer | kernel/io/ | memory/sensory/ |
| CommandHandler | iris/commands/ | kernel/commands/ |
