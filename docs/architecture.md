# Iris アーキテクチャ設計書

## 1. 全体像

Iris v0.2 は**ヘキサゴナルアーキテクチャ**（Ports & Adapters）と**イベント駆動型設計**を採用した自律型AIアシスタントです。

```
┌──────────────────────────────────────────────────────┐
│                     Adapters                          │
│  ┌──────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ CLI      │  │ API Server   │  │ GUI Client      │ │
│  │ adapter  │  │ (FastAPI)    │  │ (将来)          │ │
│  └────┬─────┘  └──────┬───────┘  └────────┬────────┘ │
├───────┴────────────────┴───────────────────┴──────────┤
│                  EventBus (インメモリ同期)              │
├───────────────────────────────────────────────────────┤
│                   Kernel (ドメイン層)                   │
│  ┌─────────────────────────────────────────────────┐  │
│  │  AgentKernel — 状態管理・異常検知・イベント統括  │  │
│  │  ProactiveEngine — 自発発話＋自律ガバナンス     │  │
│  │  ConversationService — 会話オーケストレーション │  │
│  │  Planner — タスク分解                          │  │
│  │  Executor — サブタスク逐次実行                  │  │
│  │  Reflexion — 自己反省                          │  │
│  └─────────────────────────────────────────────────┘  │
│                                                        │
│  Ports: (抽象インターフェース)                          │
│  - EventBus: publish/subscribe                         │
│  - AgentStateManager: transition/check                 │
│  - MemoryManager: search/add/get_recent                │
│  - Personality: build_system_prompt                    │
│  - ContextManager: check_and_summarize                 │
│  - Reflexion: reflect/quick_reflect                    │
│  - ToolExecutionEngine: execute_all                    │
├───────────────────────────────────────────────────────┤
│                 Infrastructure (外部サービス)           │
│  ┌──────────────┐ ┌───────────┐ ┌─────────────────────┐  │
│  │ Ollama /     │ │ ChromaDB  │ │ JSONL File Store    │  │
│  │ OpenRouter   │ │           │ │                     │  │
│  └──────────────┘ └───────────┘ └─────────────────────┘  │
└───────────────────────────────────────────────────────┘
```

## 2. レイヤードアーキテクチャ

| 層 | 責務 | 依存方向 |
|---|---|---|
| **adapters/** | ユーザーとの入出力（CLI, API, GUI） | → iris.kernel |
| **iris/kernel/** | ビジネスロジック全体 | → iris.llm, iris.memory, iris.capabilities |
| **iris/personality/** | システムプロンプト・人格シミュレーション | → iris.memory |
| **iris/memory/** | 記憶の永続化・検索・要約 | → 外部DB |
| **iris/llm/** | LLM Provider通信（Ollama/OpenRouter） | → 各LLM API |
| **iris/capabilities/** | ツールの実行・動的発見 | → 外部ツール |
| **iris/commands/** | CLIコマンドの解釈・実行（`/help`, `/sleep`, `/compact` 等） | → iris.kernel |

**依存方向は常に下向きのみ。** 上位層が下位層を直接参照しない。

## 3. イベント駆動設計

### EventBus
- **型**: 同期インメモリ（将来はRedis/NATS対応可能）
- **パターン**: publish/subscribe
- **イベント種別**: `UserInputEvent`, `ProactiveSpeechEvent`, `TimerTick`, `AgentStateChangeEvent`, `MemoryUpdateEvent`, `AgentResponseEvent`, `AgentAnomalyEvent`

### イベントフロー例

```
[TimerTick (5秒ごと)]
    → AgentKernel._on_timer()
    → ProactiveEngine.check_trigger()
    → [発話必要] → ProactiveSpeechEvent → 各アダプターに配信

[ユーザー入力]
    → UserInputEvent
    → AgentKernel._on_user_input()
    → ConversationService.process_input()
    → AgentResponseEvent → 各アダプターに配信

[スラッシュコマンド]
    → CLIAdapter.run() 内でインターセプト
    → CommandHandler.handle() で処理
    → 直接コンソールに応答表示（EventBus は経由しない）
```

## 4. ガバナンスモデル（自律発話）

### 3層アーキテクチャ

```
┌─────────────────────────────────┐
│ Tier 1: ルールベース自動許可     │ → 即時発行
│ 挨拶・定型確認・短い気遣い        │
├─────────────────────────────────┤
│ Tier 2: LLM自己判断              │ → 信頼度閾値で自動承認 or 保留
│ 話題提案・関連する記憶の共有       │
├─────────────────────────────────┤
│ Tier 3: AgentKernel介入          │ → 人間確認 or 自動抑制
│ 異常検知・過剰発話・悪循環防止    │
└─────────────────────────────────┘
```

## 5. 状態遷移

`AgentStateManager` が管理する6状態：

- **IDLE** → PROCESSING: ユーザー入力受信
- **IDLE** → PROACTIVE: TimerTick + トリガースコア > 閾値
- **IDLE** → SLEEPING: /sleep コマンド or スケジュール
- **IDLE** → THINKING: thinking_mode + 自動推論
- **PROCESSING** → IDLE: 応答完了
- **PROCESSING** → REFLECTING: Quick Reflection条件達成
- **PROACTIVE** → IDLE: 発話完了
- **REFLECTING** → IDLE: 反省完了
- **THINKING** → IDLE: 推論完了
- **SLEEPING** → IDLE: cooldown終了 or /wakeup

詳細は `docs/agent-state.md` を参照。

## 6. 記憶システム

### 3種の記憶

| 記憶種別 | 技術 | 上限 | 用途 |
|---|---|---|---|
| EpisodicStore | JSONL | 30エントリ | セッション記録、直近のやり取り |
| SemanticStore | ChromaDB + BM25 | 100エントリ | 教訓・ユーザーの好み・長期記憶 |
| PersonaProfile | JSON | 動的 | ペルソナ特性・話し方の動的変化 |

### 記憶更新フロー
```
ユーザー反応 → EpisodicStore 即時記録
             ↓ (5回ごと)
         Reflexion.quick_reflect()
             ↓
         SemanticStore 更新（教訓・好み）
             ↓ (セッション終了時)
         Reflexion.reflect() → EpisodicStore + SemanticStore
```
