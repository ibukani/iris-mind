# Iris Cognitive Runtime Architecture v1.2.1 最終設計書

## 1. 目的

Iris は、AIコンパニオン / Neuro-sama 的な自発性・記憶・関係性・突飛さを持つ AI Runtime として再設計する。

破壊的変更を許可し、既存構造との後方互換よりも、以下を優先する。

- AIコーディングエージェントが実装場所を迷わない
- ツギハギ実装を構造的に防ぐ
- Proactive / Memory / Relationship / PersonaPatch を拡張しやすくする
- Discord / Voice / Twitch / Avatar など外部アプリと疎結合にする
- 脳科学を参考にしつつ、ソフトウェアとして扱いやすい認知サイクルに落とし込む
- MVPを小さく作り、段階的に機能拡張できるようにする

---

## 2. 基本思想

Iris は「脳の部位を直接模倣するシステム」ではなく、**脳科学を参考にした認知サイクルを実行する AI コンパニオン Runtime** として設計する。

脳科学の概念は、以下のように機能へ翻訳して扱う。

| 脳科学的な参考 | Irisでの設計単位 |
|---|---|
| 作業記憶 | `WorkspaceFrame` |
| 海馬 / エピソード記憶 | `cognitive/memory/episodic` |
| 意味記憶 | `cognitive/memory/semantic` |
| 扁桃体 / 価値評価 | `cognitive/affect/appraisal` |
| 気分 | `cognitive/affect/mood` |
| 関係性評価 | `cognitive/affect/relationship` |
| 動機づけ | `cognitive/motivation` |
| 行動選択 | `cognitive/policy` |
| 抑制 | `cognitive/policy/inhibition` |
| 行動実行 | `cognitive/action` |
| 学習・記憶統合 | `cognitive/learning` + `BackgroundJob` |

中心となる流れは以下。

```text
External App
→ Observation
→ AppGateway
→ CognitiveCycle
→ typed PipelineStep results
→ WorkspaceFrame
→ ActionPlan
→ ActionSafetyGate
→ Presentation
→ PresentedOutput
→ OutputSafetyGate
→ AppAction
→ External App
→ ActionResult
→ LearningHook
→ BackgroundJob
```

---

## 3. 最終ディレクトリ構成

```text
iris/
├── core/
│   ├── ids.py
│   ├── time.py
│   ├── errors.py
│   └── result.py
│
├── contracts/
│   ├── observations.py
│   ├── actions.py
│   ├── messages.py
│   ├── identity.py
│   ├── conversation.py
│   ├── memory.py
│   ├── affect.py
│   └── commands.py
│
├── runtime/
│   ├── app.py
│   ├── config.py
│   ├── scheduler.py
│   ├── background_jobs.py
│   ├── lifecycle.py
│   ├── telemetry.py
│   └── wiring/
│       ├── cognitive.py
│       ├── adapters.py
│       ├── features.py
│       ├── presentation.py
│       └── safety.py
│
├── cognitive/
│   ├── cycle/
│   │   ├── service.py
│   │   ├── pipeline.py
│   │   ├── steps.py
│   │   ├── frame_builder.py
│   │   └── models.py
│   │
│   ├── workspace/
│   │   ├── frame.py
│   │   └── contributors.py
│   │
│   ├── perception/
│   ├── memory/
│   ├── affect/
│   ├── motivation/
│   ├── policy/
│   ├── action/
│   └── learning/
│
├── presentation/
│   ├── presenter.py
│   ├── output.py
│   └── style.py
│
├── features/
│   ├── chat/
│   ├── proactive_talk/
│   ├── memory_consolidation/
│   ├── relationship_update/
│   ├── persona_patch/
│   └── command_control/
│
├── adapters/
│   ├── app_gateway/
│   ├── llm/
│   ├── stores/
│   ├── tools/
│   ├── embeddings/
│   └── external_clients/
│
├── safety/
│   ├── action_gate.py
│   ├── output_filter.py
│   └── policy_engine.py
│
└── admin/
```

---

## 4. 各層の責務

### 4.1 `core/`

最下層の共通基盤。

置いてよいもの。

- 共通ID
- 時刻
- Result型
- 共通エラー
- 型ユーティリティ

置いてはいけないもの。

- 記憶処理
- 会話処理
- LLM処理
- Adapter処理
- Feature共通処理

`core/` は便利箱にしない。

---

### 4.2 `contracts/`

層間で共有する型を置く。

主な責務。

- `Observation`
- `Action`
- `Message`
- `Identity`
- `Conversation`
- `Memory`
- `Affect`
- `Command`

注意点。

- `contracts/ports.py` は原則作らない。
- Port は利用側モジュールの近くに置く。
- `contracts/events.py` は初期構成では作らない。
- EventBus 的な逃げ道を復活させない。

Port の配置例。

```text
cognitive/action/ports.py
cognitive/memory/ports.py
presentation/ports.py
safety/ports.py
adapters/app_gateway/ports.py
```

---

### 4.3 `runtime/`

アプリケーション起動、構成、スケジューリング、バックグラウンドジョブを担当する。

主な責務。

- アプリ起動
- 設定読み込み
- dependency wiring
- scheduler
- background job
- lifecycle
- telemetry

注意点。

- `runtime/composition.py` 1ファイルにすべて詰め込まない。
- `runtime/wiring/` に分割する。
- `runtime/wiring/` は constructor injection に限定する。
- `runtime/wiring/` に業務ロジックや認知ロジックを書かない。

`runtime` だけが全体を知ってよい。

---

### 4.4 `cognitive/`

Iris の中核。認知サイクル、記憶、感情、動機、行動選択、学習を担当する。

中心は `CognitiveCycle`。

```python
class CognitiveCycle:
    async def run(self, observation: Observation) -> CycleResult:
        ...
```

ただし、`CognitiveCycle` は God Service にしない。
処理本体ではなく pipeline coordinator として実装する。

基本フロー。

```text
Observation
→ PerceptionStep
→ MemoryRetrievalStep
→ AppraisalStep
→ MotivationStep
→ PlanningStep
→ ActionSelectionStep
→ ActionPlan
```

重要ルール。

- cognitive module 同士は直接呼び合わない。
- `CognitiveCycle` が順序制御する。
- 各 PipelineStep は `WorkspaceFrame` を直接 mutate しない。
- 各 PipelineStep は typed result を返す。
- `FrameBuilder` が typed result を `WorkspaceFrame` に統合する。

悪い例。

```text
memory → affect を直接呼ぶ
affect → policy を直接呼ぶ
policy → action を直接呼ぶ
```

良い例。

```text
CognitiveCycle → memory step
CognitiveCycle → affect step
CognitiveCycle → motivation step
CognitiveCycle → policy step
CognitiveCycle → action step
```

---

### 4.5 `workspace/`

1ターン中の状態を集約する。

`WorkspaceFrame` は、会話ターン内で各認知モジュールが共有する typed snapshot である。

入れてよいもの。

- observation
- interpreted input
- identity context
- conversation context
- retrieved memory summary
- affect state
- relationship snapshot
- motivation state
- goals
- constraints
- candidate actions

入れてはいけないもの。

- storeそのもの
- adapterそのもの
- manager参照
- 過去ログ全体
- 巨大な `dict[str, Any]`
- LLM prompt 文字列だけの巨大 context

`WorkspaceFrame` は「何でも入る箱」にしない。

---

### 4.6 `presentation/`

`cognitive/` が決めた `ActionPlan` を、実際にどのような形で見せるかに変換する。

MVPでは軽量でよい。

```text
ActionPlan
→ SimplePresenter
→ PresentedOutput
```

将来、Neuro-sama 的な配信者・演出層に発展させる。

```text
ActionPlan
→ PerformanceDirector
→ Text + Voice + Expression + Timing
```

責務分離。

```text
cognitive/      = 何をしたいかを決める
presentation/   = どう見せるかを決める
adapters/       = どこへ送るかを担当する
```

---

### 4.7 `features/`

新機能を縦切りで追加する場所。

ただし、`features/` は好き勝手に内部実装を改造する場所ではない。
`CognitiveCycle` の拡張ポイントに参加する extension provider である。

各 feature は `features/<name>/feature.py` を持ち、`FeatureDefinition` を返す。

例。

```python
@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    observation_sources: list[ObservationSource]
    workspace_contributors: list[WorkspaceContributor]
    appraisal_providers: list[AppraisalProvider]
    salience_scorers: list[SalienceScorer]
    goal_proposers: list[GoalProposer]
    policy_constraints: list[PolicyConstraint]
    action_providers: list[ActionProvider]
    learning_hooks: list[LearningHook]
    background_jobs: list[BackgroundJob]
```

`runtime/wiring/features.py` は `FeatureDefinition` を集めて登録するだけにする。

新機能は、次のいずれかの拡張ポイントとして追加する。

- ObservationSource
- WorkspaceContributor
- MemoryRetriever
- AppraisalProvider
- SalienceScorer
- GoalProposer
- PolicyConstraint
- ActionProvider
- LearningHook
- BackgroundJob
- Presenter
- SafetyGate
- Adapter

例。

```text
Proactive
→ ObservationSource
→ SalienceScorer
→ GoalProposer
→ PolicyConstraint
→ ActionProvider

Relationship
→ AppraisalProvider
→ LearningHook

PersonaPatch
→ BackgroundJob
→ LearningHook

Neuro-sama 的な突飛さ
→ Presenter
→ GoalProposer
→ PolicyConstraint
→ SafetyGate
```

---

### 4.8 `adapters/`

外部技術との接続を担当する。

`adapters/app_gateway/` は旧 `io/` ではない。
責務は、外部アプリとの `Observation / AppAction / ActionResult` protocol boundary である。

`adapters/llm/` は LLM 技術境界である。
責務は、typed `LLMRequest` を受け取り typed `LLMResponse` を返すことに限定する。
実プロバイダ呼び出し、モデル選択、認証、ネットワーク I/O は adapter 境界の外へ漏らさない。
テストと local MVP は deterministic な `FakeLLMClient` を使う。
OpenAI provider は `adapters/llm/openai.py` に置き、Responses API との変換を adapter 内に閉じ込める。
real provider configuration は typed config で明示注入し、global discovery や service locator は使わない。
provider tests は `FakeLLMClient` または mocked provider client を使い、実ネットワークへ接続しない。
`cognitive/` は `adapters/llm/` を import せず、runtime wiring が constructor injection で接続する。

`adapters/memory/` は memory store 技術境界である。
責務は、typed `MemoryQuery` を受け取り typed `MemorySearchResult` を返すことに限定する。
テストと local MVP は deterministic な `FakeMemoryStore` を使う。
LangChain / LangMem / vector store は `MemoryStore` 背後の optional adapter としてだけ扱う。
`cognitive/` は `MemoryQuery` と `MemorySearchResult` だけに依存し、LangChain、LangMem、vector DB SDK、adapter 型を import しない。
`runtime/wiring/` は constructor injection で adapter を明示的に組み立てる。
LangChain adapter は LangChain document / vectorstore 型を Iris contracts に漏らさない薄い変換層である。
In-memory vector adapter は外部サービスなしの deterministic adapter に限定する。
LangMem promotion / consolidation、実 embeddings provider、vector DB persistence、旧 LangChain memory API の core memory 化は後続 phase まで入れない。
`cognitive/memory/` は store 実装を import せず、runtime wiring が constructor injection で接続する。

AppGateway の責務。

- 外部アプリから Observation を受け取る
- 外部アプリへ AppAction を返す
- ActionResult を受け取る
- correlation_id / turn_id / session_id を管理する
- external ref と Iris internal ref を対応づける

AppGateway がやってはいけないこと。

- cognitive 判断
- 記憶更新
- Proactive 判断
- presentation 判断
- Discord / Voice 固有ロジックの深い実装

Discord の具体 API 操作は `iris-discord-bot` 側。
Voice / TTS / STT の具体処理は `iris-voice-runtime` 側。

---

### 4.9 `safety/`

システムとして危険な出力や外部操作を止める。

v1.2.1 では safety を2段階に分ける。

```text
ActionSafetyGate:
- 外部送信してよいか
- tool を使ってよいか
- proactive 発話してよいか
- 権限が必要な操作ではないか

OutputSafetyGate:
- 実際の文面が危険ではないか
- プラットフォームに出してよい表現か
- 個人情報や過激表現が含まれていないか
```

構成。

```text
safety/
├── action_gate.py
├── output_filter.py
└── policy_engine.py
```

`cognitive/policy/inhibition` との違い。

```text
cognitive inhibition:
- 今は話さない
- しつこくしない
- 会話のテンポを守る
- キャラとして抑制する

safety:
- 危険な出力を止める
- 権限のない操作を止める
- 外部送信前に検査する
- 監査ログを残す
```

---

## 5. 主要な型の責務

### 5.1 `Observation`

外部世界または内部スケジューラから Iris に入る入力。

例。

- `UserMessageObservation`
- `TranscriptObservation`
- `IdleTickObservation`
- `AudienceMessageObservation`
- `GameEventObservation`

Discord / Voice / Twitch などの具体イベントは、外部アプリまたは AppGateway で Observation に変換する。

---

### 5.2 `WorkspaceFrame`

1ターン中の typed snapshot。
PipelineStep の結果を `FrameBuilder` が統合して作る。

---

### 5.3 `ActionPlan`

Iris が「何をしたいか」を表す。
まだ外部アプリ固有ではない。

LLM-backed response generation は `cognitive/action/response.py` の PipelineStep として扱う。
この step は `WorkspaceFrame` から typed response prompt を作り、注入された response generator から得た text を `ActionPlan.candidate_text` に入れる。
`WorkspaceFrame` は直接変更せず、`ActionSelectionResult` を返して `FrameBuilder` に統合させる。
LLM provider 形状への変換は `runtime/wiring/llm.py` が担当する。

例。

```text
ユーザーに返答したい
会話を続けたい
今は発話しない
tool を使いたい
```

---

### 5.4 `PresentedOutput`

ActionPlan を「どう見せるか」に変換したもの。

例。

```text
text
style
emotion_hint
expression_hint
timing
priority
interruptible
```

---

### 5.5 `AppAction`

外部アプリが実行できる具体命令。

例。

```text
SendMessageAction
SpeakAction
StopSpeechAction
SetAvatarExpressionAction
ToolCallAction
```

---

### 5.6 `ActionResult`

外部アプリが実際に Action を実行した結果。

最低限必要な情報。

```text
- action_id
- correlation_id
- status: succeeded / failed / cancelled / blocked
- delivered_at
- error_reason
- external_message_id
```

Learning は ActionResult を受けてから行う。

---

## 6. 外部アプリとの関係

Iris 本体は `Cognitive Runtime` として設計する。
Discord Bot、Voice Runtime、Twitch Client などは外部アプリとして分離する。

推奨構成。

```text
iris-core = Cognitive Runtime
iris-discord-bot = Discord App Runtime
iris-voice-runtime = Voice / Media Runtime
iris-twitch-client = Stream App Runtime
```

### Iris 本体の責務

- 入力を Observation として解釈する
- 会話状態を管理する
- 記憶を検索・更新する
- 関係性を評価する
- 返答方針を決める
- Proactive 発話を決める
- ActionPlan を作る
- 安全検査をする

### 外部アプリの責務

- Discord API / 音声 / Twitch / Avatar などに接続する
- 外部イベントを Observation に変換する
- Iris から返された AppAction を実行する
- ActionResult を返す
- rate limit / reconnect / platform 固有処理を扱う

外部アプリがやってはいけないこと。

- 返答内容を決める
- Proactive 発話するか決める
- 記憶を更新する
- 関係性を更新する
- キャラ性を決める
- 重要度判断を独自に行う

外部アプリは、外部世界と Iris の翻訳機である。

---

## 7. 依存方向

基本依存方向。

```text
contracts → core

cognitive → contracts, core

presentation → contracts, core

features → contracts, cognitive extension protocols, core

adapters → contracts, core

safety → contracts, core

runtime → cognitive, features, adapters, presentation, safety, contracts, core
```

禁止。

```text
cognitive → adapters
cognitive → runtime
cognitive → features
contracts → cognitive
contracts → adapters
features → adapters 原則禁止
adapters → cognitive 原則禁止
```

`runtime` だけが全体を知ってよい。
それ以外の層は依存方向を守る。

---

## 8. 廃止する既存構造

破壊的変更を許可するため、以下は中心設計として温存しない。

- PluginManager 中心の設計
- PluginProtocol / MANIFEST / plugin export 前提
- EventBus による主制御
- `iris/event/event_types.py` の互換 shim
- `iris/io/events.py` を共有イベント置き場にする構造
- `builder.py` に横断組み立てが集まる構造
- dispatcher の `action: str` 分岐
- memory / limbic / agency が暗黙に EventBus で連携する構造

EventBus は初期設計に入れない。
必要になっても、主制御には使わない。

許可される用途。

- lifecycle
- telemetry
- audit
- background job notification
- diagnostics

禁止される用途。

- CognitiveCycle の主制御
- memory → affect → policy の順序制御
- 隠れた manager 連携

---

## 9. 既存コードの移行先

| 既存 | 移行先 | 方針 |
|---|---|---|
| `kernel/` | `runtime/` | PluginManager 中心を廃止し、composition root にする |
| `event/` | 原則廃止 / 必要なら telemetry・audit用途 | 主制御では使わない |
| `io/` | `adapters/app_gateway/` | 外部アプリとの境界へ |
| `account/` | `contracts/identity.py` / context service | ユーザー識別・関係性の土台 |
| `room/` | `contracts/conversation.py` | conversation / session として再定義 |
| `memory/` | `cognitive/memory/` + `features/memory_consolidation/` + `adapters/stores/` | 記憶ロジックを責務ごとに分解 |
| `limbic/` | `cognitive/affect/` | appraisal / mood / relationship として移行 |
| `agency/` | `cognitive/policy/` + `cognitive/action/` | planning / inhibition / execution に分解 |
| `llm/` | `adapters/llm/` + `cognitive/action/response.py` | LLM は port 経由 |
| `tools/` | `adapters/tools/` + `cognitive/action/tool_use.py` | tool 実行は action と adapter に分ける |
| `heartbeat/` | `runtime/scheduler.py` | TimerTick ではなく ObservationSource 化 |
| `admin/` | `admin/` | 必要に応じて維持 |

---

## 10. MVP 実装順

全面置き換えでも、最初から全部作らない。
最初に作るのは完成版 Iris ではなく、v1.2.1 の骨格で1ターン会話が通る最小 Cognitive Runtime。

### Phase 0: v1.2.1 設計固定

作るもの。

```text
docs/architecture/cognitive-runtime-v1.2.1.md
AGENTS.md の最小更新
AIコーディング向けルール
```

---

### Phase 1: architecture test 先行

最初にテストを作る。

```text
tests/architecture/
├── test_dependency_direction.py
├── test_no_adapter_import_from_cognitive.py
├── test_no_runtime_import_from_cognitive.py
├── test_no_feature_import_from_cognitive.py
├── test_no_service_locator.py
├── test_no_eventbus_main_flow.py
├── test_feature_extension_boundaries.py
└── test_no_any_context.py
```

最低限検査すること。

- cognitive から adapters import 禁止
- cognitive から runtime import 禁止
- cognitive から features import 禁止
- contracts から cognitive import 禁止
- runtime/wiring 以外で service locator 禁止
- EventBus.subscribe による CognitiveCycle 主制御禁止
- action: str の dispatcher 分岐禁止
- WorkspaceFrame で `dict[str, Any]` 禁止
- builder が `dict[str, object]` を返すことを禁止
- features は FeatureDefinition 経由で登録する

---

### Phase 2: v2 scaffold

最小ディレクトリを作る。

```text
iris/
├── core/
├── contracts/
├── runtime/
├── cognitive/
│   ├── cycle/
│   ├── workspace/
│   ├── perception/
│   └── action/
├── presentation/
├── safety/
└── adapters/
    └── app_gateway/
```

最低限必要な型。

```text
Observation
WorkspaceFrame
PipelineStepResult
ActionPlan
PresentedOutput
AppAction
ActionResult
```

---

### Phase 3: 最小会話ループ

Fake LLM か既存 LLM adapter の薄い wrapper で、1ターン通す。

```text
Text input
→ UserMessageObservation
→ CognitiveCycle
→ ActionPlan
→ SimplePresenter
→ SendMessageAction
→ ActionResult
```

---

### Phase 4: LLM 移植

既存の `iris/llm` は再利用価値が高い。

移行先。

```text
iris/llm/providers/*
→ adapters/llm/

LLMBridge / prompt building の一部
→ cognitive/action/response.py
```

ただし、`cognitive/action` は具体 provider を知らない。

```text
cognitive/action
→ LLMPort

adapters/llm
→ Ollama / OpenAI-compatible / Fake
```

---

### Phase 5: memory 移植

最初は軽く入れる。

```text
working memory
episodic append
basic retrieval
```

重いものは後回し。

```text
LangMem
promotion
reflection
persona patch
```

これらは `features/memory_consolidation` と `BackgroundJob` に回す。

---

### Phase 6: affect / relationship 移植

旧 `limbic/` を移行する。

```text
limbic/appraiser.py
limbic/mood.py
limbic/relationship.py
→ cognitive/affect/
```

ただし、`affect` が `memory` や `policy` を直接呼ばないようにする。
`CognitiveCycle` が順番に呼ぶ形にする。

Phase 6 の affect / relationship は既存の `AffectSnapshot`、
`RelationshipSnapshot`、`AppraisalResult`、`RelationshipResult` を再利用する。
keyword-based appraisal が最小の VAD-like 値と `affect_summary` を作り、
`FrameBuilder` が immutable な `WorkspaceFrame.affect` に写す。
mood dynamics は明示的な `elapsed_seconds` を受ける純粋な減衰/更新関数とし、
永続 mood store や global singleton は持たない。
relationship は明示的に注入された per-user state に限定し、trust / affinity /
familiarity と `relationship_summary` を `WorkspaceFrame.relationship` に写す。
response generation はこの typed frame context を短く prompt context に含めるだけで、
persona、agency policy、proactive behavior は決めない。

移行対象外:

- neural emotion classifier
- LimbicOrchestrator / LimbicPlugin / EventBus affect flow
- appraisal / relationship persistence
- full Lazarus appraisal
- attachment style
- disclosure depth
- emotion history
- agency modulation / inhibition
- LangMem promotion / memory consolidation

---

### Phase 7: policy / inhibition 移植

旧 `agency/` を分解する。

```text
agency/planning
→ cognitive/policy/

agency/inhibition
→ cognitive/policy/inhibition

agency/execution
→ cognitive/action/

tool execution
→ cognitive/action/tool_use.py + adapters/tools/
```

---

### Phase 8: proactive 実装

Proactive は新設計で作り直す。

```text
features/proactive_talk/
├── feature.py
├── observations.py
├── salience.py
├── goals.py
├── policy.py
└── actions.py
```

流れ。

```text
IdleTickObservation
→ CognitiveCycle
→ SalienceScorer
→ GoalProposer
→ PolicyConstraint
→ SpeakAction or NoAction
```

---

### Phase 9: 旧構造削除

削除対象。

- PluginManager
- plugin manifests
- EventBus 主制御
- event_types shim
- dispatcher action 分岐
- 古い architecture tests

---

## 11. Learning と BackgroundJob

Learning は ActionResult 後に行う。

```text
ActionPlan
→ Presentation
→ SafetyGate
→ Adapter
→ ActionResult
→ LearningHook
```

理由。

- 送信成功したか
- 失敗したか
- safety で blocked されたか
- user interrupt により cancelled されたか

を見てから記憶や関係性を更新する必要がある。

### LearningHook

hot path で実行する軽量処理。

- 会話ログの追加
- working memory 更新
- relationship の軽い更新
- background job の enqueue

### BackgroundJob

hot path から外す重い処理。

- 長期記憶抽出
- LangMem extraction
- persona patch proposal
- episodic → semantic promotion
- 重い reflection

---

## 12. Proactive の設計

Proactive は特殊な別システムではなく、内部 Observation から始まる CognitiveCycle として扱う。

```text
Scheduler
→ IdleTickObservation
→ CognitiveCycle
→ WorkspaceFrame
→ SalienceScorer
→ GoalProposer
→ PolicyConstraint
→ ActionProvider
→ SpeakAction or NoAction
```

`features/proactive_talk/` が直接 memory や policy の内部実装を改造してはいけない。

---

## 13. Neuro-sama 的拡張

最初から巨大な `performance/` は作らない。
まず `presentation/` を置く。

MVP。

```text
ActionPlan
→ SimplePresenter
→ PresentedOutput
```

将来。

```text
ActionPlan
→ PerformanceDirector
→ Text + Voice + Expression + Timing
```

将来の構成。

```text
performance/
├── director.py
├── pacing.py
├── bit_engine.py
├── audience.py
├── stream_state.py
├── expression.py
└── moderation.py
```

突飛さは prompt だけに任せない。
以下の組み合わせで制御する。

```text
GoalProposer
+ Presenter / PerformanceDirector
+ PolicyConstraint
+ SafetyGate
```

---

## 14. AIコーディング向けルール

AIコーディングエージェントには、以下のルールを必ず守らせる。

1. 主処理は CognitiveCycle が明示的に制御する。
2. CognitiveCycle は God Service ではなく pipeline coordinator とする。
3. 各 PipelineStep は WorkspaceFrame を直接 mutate しない。
4. 各 PipelineStep は typed result を返す。
5. FrameBuilder が StepResult を WorkspaceFrame に統合する。
6. 外部入力はすべて Observation に変換する。
7. 外部出力は ActionPlan → ActionSafetyGate → Presentation → OutputSafetyGate → AppAction の順に通す。
8. Learning は ActionResult を受けてから行う。
9. cognitive/ は adapters/ と runtime/ を import しない。
10. cognitive/ は features/ を import しない。
11. features/ は FeatureDefinition による extension provider として登録する。
12. features/ は cognitive 内部を直接改造しない。
13. EventBus は初期設計に入れない。必要になっても主制御には使わない。
14. Service Locator / resolve_optional / グローバル registry 呼び出しを禁止する。
15. 新機能は features/<name>/ に縦切りで追加する。
16. 互換 shim・一時 wrapper・旧API維持は原則作らない。
17. dispatcher の action: str 分岐を増やさない。
18. dict[str, Any] や dict[str, object] を内部境界に使わない。
19. runtime/wiring は constructor injection のみにする。
20. 依存方向は architecture test で強制する。

---

## 15. Go / No-Go 条件

### Go 条件

以下を守るなら実装に入ってよい。

- v1.2.1 設計を固定する
- architecture test を先に置く
- 最初のMVPを text-only / FakeLLM までに絞る
- 旧構造を温存しようとしない
- 互換 shim を作らない
- 既存コードは部品として移植する

### No-Go 条件

以下の方針なら止める。

- 旧 Plugin/EventBus 構造と v1.2.1 を長期共存させる
- 既存テストを全部通すために互換層を作る
- 最初から memory / affect / proactive まで全部入れる
- CognitiveCycle に全部の処理を書く
- features から cognitive 内部を直接改造する

---

---

## 16. v1.2.1 で追加する実装固定ルール

v1.2.1 は、v1.2 の方針を変えるものではない。
目的は、AIコーディングエージェントが実装時に迷いやすい抽象部分を、最低限の型・境界・禁止例まで落とし込むことである。

v1.2.1 で追加する固定ルール。

1. `CognitiveCycle.run()` は pipeline coordinator に限定する。
2. `CognitiveCycle.run()` に LLM prompt 構築、記憶更新、関係性更新、adapter 呼び出し、safety 判定を書かない。
3. `PipelineStep` は `WorkspaceFrame` を受け取り、typed `PipelineStepResult` を返す。
4. `PipelineStep` は `WorkspaceFrame` を mutate しない。
5. `FrameBuilder` だけが step result を統合して次の `WorkspaceFrame` を作る。
6. MVP の `FeatureDefinition` は最小フィールドから開始し、未使用 extension point の空実装を量産しない。
7. `dict[str, Any]`、`dict[str, object]`、`action: str` dispatcher、service locator は内部境界では使わない。
8. 旧構造の互換 wrapper を作るより、既存コードを責務単位で移植する。

---

## 17. Minimal Interface Specification

この章は、AIコーディングエージェントに最初に実装させる最小インターフェース仕様である。
実装開始時は、この章の型を優先し、ファイルごとに独自型を増やさない。

### 17.1 `core/ids.py`

```python
from typing import NewType

ObservationId = NewType("ObservationId", str)
ActionId = NewType("ActionId", str)
TurnId = NewType("TurnId", str)
SessionId = NewType("SessionId", str)
ConversationId = NewType("ConversationId", str)
UserId = NewType("UserId", str)
CorrelationId = NewType("CorrelationId", str)
ExternalRef = NewType("ExternalRef", str)
```

ID はただの `str` と混同しない。
外部アプリの ID は `ExternalRef` として扱い、Iris 内部 ID と直接混ぜない。

### 17.2 `contracts/identity.py`

```python
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from iris.core.ids import UserId, ExternalRef

@dataclass(frozen=True)
class Identity:
    user_id: UserId
    display_name: str
    provider: str
    provider_subject: ExternalRef
    metadata: Mapping[str, str] = MappingProxyType({})
```

`metadata` は外部由来の補助情報に限定する。
認知判断に使う状態を `metadata` に押し込まない。

### 17.3 `contracts/observations.py`

```python
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from iris.contracts.identity import Identity
from iris.core.ids import ObservationId, SessionId, ExternalRef

class ObservationKind(StrEnum):
    USER_MESSAGE = "user_message"
    TRANSCRIPT = "transcript"
    IDLE_TICK = "idle_tick"
    AUDIENCE_MESSAGE = "audience_message"
    GAME_EVENT = "game_event"

@dataclass(frozen=True)
class Observation:
    observation_id: ObservationId
    session_id: SessionId
    actor: Identity | None
    occurred_at: datetime
    kind: ObservationKind

@dataclass(frozen=True)
class UserMessageObservation(Observation):
    text: str
    external_message_id: ExternalRef | None = None

@dataclass(frozen=True)
class IdleTickObservation(Observation):
    reason: str
```

外部アプリ固有のイベント名を `cognitive/` に入れない。
Discord、Twitch、Voice などのイベントは AppGateway 側で `Observation` に変換する。

### 17.4 `contracts/actions.py`

```python
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from iris.core.ids import ActionId, CorrelationId, SessionId, ExternalRef

class ActionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"

@dataclass(frozen=True)
class ActionPlan:
    turn_intent: str
    candidate_text: str | None
    should_respond: bool
    priority: int
    interruptible: bool = True

@dataclass(frozen=True)
class PresentedOutput:
    text: str | None
    style_hint: str | None = None
    emotion_hint: str | None = None
    expression_hint: str | None = None
    delay_ms: int = 0
    priority: int = 0
    interruptible: bool = True

@dataclass(frozen=True)
class AppAction:
    action_id: ActionId
    session_id: SessionId
    correlation_id: CorrelationId

@dataclass(frozen=True)
class SendMessageAction(AppAction):
    text: str

@dataclass(frozen=True)
class NoAction(AppAction):
    reason: str

@dataclass(frozen=True)
class ActionResult:
    action_id: ActionId
    correlation_id: CorrelationId
    status: ActionStatus
    delivered_at: datetime | None = None
    external_message_id: ExternalRef | None = None
    error_reason: str | None = None
```

`ActionPlan` は「何をしたいか」、`PresentedOutput` は「どう見せるか」、`AppAction` は「外部アプリが実行する命令」である。
この3つを混ぜない。

### 17.5 `cognitive/workspace/frame.py`

```python
from dataclasses import dataclass, field

from iris.contracts.observations import Observation
from iris.contracts.actions import ActionPlan

@dataclass(frozen=True)
class InterpretedInput:
    text: str | None
    language: str | None
    intent_hint: str | None = None

@dataclass(frozen=True)
class MemorySummary:
    retrieved_memories: tuple[MemorySearchResult, ...] = ()

@dataclass(frozen=True)
class AffectSnapshot:
    mood_label: str | None = None
    arousal: float = 0.0
    valence: float = 0.0

@dataclass(frozen=True)
class RelationshipSnapshot:
    user_label: str | None = None
    affinity: float = 0.0
    trust: float = 0.0
    familiarity: float = 0.0

@dataclass(frozen=True)
class GoalCandidate:
    name: str
    reason: str
    priority: int

@dataclass(frozen=True)
class PolicyConstraint:
    name: str
    reason: str
    blocks_response: bool = False

@dataclass(frozen=True)
class WorkspaceFrame:
    observation: Observation
    interpreted_input: InterpretedInput | None = None
    memory_summary: MemorySummary = field(default_factory=MemorySummary)
    affect: AffectSnapshot = field(default_factory=AffectSnapshot)
    relationship: RelationshipSnapshot = field(default_factory=RelationshipSnapshot)
    goals: tuple[GoalCandidate, ...] = ()
    constraints: tuple[PolicyConstraint, ...] = ()
    candidate_action_plans: tuple[ActionPlan, ...] = ()
```

`WorkspaceFrame` は frozen dataclass とする。
更新したい場合は `FrameBuilder` が新しい frame を返す。

禁止例。

```python
frame.context["memory"] = memory_store
frame.extra["relationship_manager"] = manager
frame.prompt = huge_prompt_text
```

### 17.6 `cognitive/cycle/models.py`

```python
from dataclasses import dataclass
from enum import StrEnum

from iris.contracts.actions import ActionPlan
from iris.cognitive.workspace.frame import WorkspaceFrame

class StepStatus(StrEnum):
    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"

@dataclass(frozen=True)
class PipelineStepResult:
    step_name: str
    status: StepStatus
    reason: str | None = None

@dataclass(frozen=True)
class PerceptionResult(PipelineStepResult):
    text: str | None = None
    language: str | None = None
    intent_hint: str | None = None

@dataclass(frozen=True)
class MemoryRetrievalResult(PipelineStepResult):
    memories: tuple[MemorySearchResult, ...] = ()

@dataclass(frozen=True)
class AppraisalResult(PipelineStepResult):
    mood_label: str | None = None
    arousal: float = 0.0
    valence: float = 0.0

@dataclass(frozen=True)
class RelationshipResult(PipelineStepResult):
    user_label: str | None = None
    affinity: float = 0.0
    trust: float = 0.0
    familiarity: float = 0.0

@dataclass(frozen=True)
class MotivationResult(PipelineStepResult):
    goals: tuple[str, ...] = ()

@dataclass(frozen=True)
class PolicyResult(PipelineStepResult):
    constraints: tuple[str, ...] = ()
    response_allowed: bool = True

@dataclass(frozen=True)
class ActionSelectionResult(PipelineStepResult):
    action_plans: tuple[ActionPlan, ...] = ()

@dataclass(frozen=True)
class CycleResult:
    frame: WorkspaceFrame
    selected_plan: ActionPlan
```

各 result は必要になった時点で分割してよい。
ただし、`dict` で代用しない。

### 17.7 `cognitive/cycle/pipeline.py`

```python
from typing import Protocol, TypeVar, Generic

from iris.cognitive.cycle.models import PipelineStepResult
from iris.cognitive.workspace.frame import WorkspaceFrame

ResultT = TypeVar("ResultT", bound=PipelineStepResult)

class PipelineStep(Protocol, Generic[ResultT]):
    name: str

    async def run(self, frame: WorkspaceFrame) -> ResultT:
        ...
```

Step は store、adapter、manager を直接持ってもよいが、それは constructor injection で受け取る。
グローバル registry から取り出してはいけない。

### 17.8 `cognitive/cycle/frame_builder.py`

```python
from dataclasses import replace

from iris.cognitive.cycle.models import (
    PipelineStepResult,
    PerceptionResult,
    MemoryRetrievalResult,
    AppraisalResult,
    RelationshipResult,
    MotivationResult,
    PolicyResult,
    ActionSelectionResult,
)
from iris.cognitive.workspace.frame import (
    WorkspaceFrame,
    InterpretedInput,
    MemorySummary,
    AffectSnapshot,
    RelationshipSnapshot,
    GoalCandidate,
    PolicyConstraint,
)

class FrameBuilder:
    def apply(self, frame: WorkspaceFrame, result: PipelineStepResult) -> WorkspaceFrame:
        match result:
            case PerceptionResult():
                return replace(
                    frame,
                    interpreted_input=InterpretedInput(
                        text=result.text,
                        language=result.language,
                        intent_hint=result.intent_hint,
                    ),
                )
            case MemoryRetrievalResult():
                return replace(
                    frame,
                    memory_summary=MemorySummary(retrieved_memories=result.memories),
                )
            case AppraisalResult():
                return replace(
                    frame,
                    affect=AffectSnapshot(
                        mood_label=result.mood_label,
                        arousal=result.arousal,
                        valence=result.valence,
                    ),
                )
            case RelationshipResult():
                return replace(
                    frame,
                    relationship=RelationshipSnapshot(
                        user_label=result.user_label,
                        affinity=result.affinity,
                        trust=result.trust,
                        familiarity=result.familiarity,
                    ),
                )
            case MotivationResult():
                return replace(
                    frame,
                    goals=tuple(
                        GoalCandidate(name=goal, reason="pipeline", priority=index)
                        for index, goal in enumerate(result.goals)
                    ),
                )
            case PolicyResult():
                return replace(
                    frame,
                    constraints=tuple(
                        PolicyConstraint(name=item, reason="pipeline")
                        for item in result.constraints
                    ),
                )
            case ActionSelectionResult():
                return replace(frame, candidate_action_plans=result.action_plans)
            case _:
                raise TypeError(f"Unsupported step result: {type(result).__name__}")
```

`FrameBuilder` にも業務ロジックを書かない。
役割は result を frame に写すことだけである。

### 17.9 `cognitive/cycle/service.py`

```python
from collections.abc import Sequence

from iris.contracts.actions import ActionPlan
from iris.contracts.observations import Observation
from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import CycleResult, PipelineStepResult
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import WorkspaceFrame

class CognitiveCycle:
    def __init__(
        self,
        steps: Sequence[PipelineStep[PipelineStepResult]],
        frame_builder: FrameBuilder,
        fallback_plan: ActionPlan,
    ) -> None:
        self._steps = tuple(steps)
        self._frame_builder = frame_builder
        self._fallback_plan = fallback_plan

    async def run(self, observation: Observation) -> CycleResult:
        frame = WorkspaceFrame(observation=observation)

        for step in self._steps:
            result = await step.run(frame)
            frame = self._frame_builder.apply(frame, result)

        selected = self._select_action_plan(frame)
        return CycleResult(frame=frame, selected_plan=selected)

    def _select_action_plan(self, frame: WorkspaceFrame) -> ActionPlan:
        if frame.candidate_action_plans:
            return max(frame.candidate_action_plans, key=lambda plan: plan.priority)
        return self._fallback_plan
```

`CognitiveCycle` が許される処理は、順序制御、result 収集、frame 更新委譲、最終 plan 選択だけである。

禁止。

```python
prompt = build_prompt(frame)
text = await openai_client.chat(prompt)
memory_store.save(...)
relationship_manager.update(...)
discord_client.send(...)
```

### 17.10 `features/definition.py`

MVP では、`FeatureDefinition` を小さく始める。

```python
from dataclasses import dataclass
from collections.abc import Sequence
from typing import Protocol

from iris.contracts.actions import ActionResult
from iris.contracts.observations import Observation
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.cycle.models import PipelineStepResult

class ObservationSource(Protocol):
    async def poll(self) -> Observation | None:
        ...

class LearningHook(Protocol):
    async def after_action_result(self, result: ActionResult) -> None:
        ...

class BackgroundJob(Protocol):
    name: str

    async def run_once(self) -> None:
        ...

@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    pipeline_steps: Sequence[PipelineStep[PipelineStepResult]] = ()
    observation_sources: Sequence[ObservationSource] = ()
    learning_hooks: Sequence[LearningHook] = ()
    background_jobs: Sequence[BackgroundJob] = ()
```

Phase 2 以降で必要になったら、以下を追加する。

```text
workspace_contributors
appraisal_providers
salience_scorers
goal_proposers
policy_constraints
action_providers
presenters
safety_gates
```

最初から空の extension point を大量に作らない。

### 17.11 `presentation/presenter.py`

```python
from typing import Protocol

from iris.contracts.actions import ActionPlan, PresentedOutput

class Presenter(Protocol):
    async def present(self, plan: ActionPlan) -> PresentedOutput:
        ...

class SimplePresenter:
    async def present(self, plan: ActionPlan) -> PresentedOutput:
        return PresentedOutput(
            text=plan.candidate_text,
            priority=plan.priority,
            interruptible=plan.interruptible,
        )
```

`presentation/` は LLM provider や Discord API を知らない。

### 17.12 `safety/action_gate.py` と `safety/output_filter.py`

```python
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from iris.contracts.actions import ActionPlan, PresentedOutput

class GateDecision(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"

@dataclass(frozen=True)
class SafetyDecision:
    decision: GateDecision
    reason: str | None = None

class ActionSafetyGate(Protocol):
    async def check_plan(self, plan: ActionPlan) -> SafetyDecision:
        ...

class OutputSafetyGate(Protocol):
    async def check_output(self, output: PresentedOutput) -> SafetyDecision:
        ...
```

MVP では常に allow する実装でよい。
ただし、呼び出し順序だけは最初から固定する。

### 17.13 `adapters/app_gateway/ports.py`

```python
from typing import Protocol

from iris.contracts.actions import AppAction, ActionResult
from iris.contracts.observations import Observation

class AppGateway(Protocol):
    async def receive_observation(self) -> Observation | None:
        ...

    async def execute(self, action: AppAction) -> ActionResult:
        ...
```

AppGateway は cognitive 判断をしない。
外部世界と Iris 内部 contract の翻訳だけを担当する。

---

## 18. MVP Scope Lock

v1.2.1 の最初の実装では、完成版 Iris を作らない。
AIコーディングエージェントには、以下のスコープを固定して渡す。

### 18.1 MVP で作るもの

```text
core/ids.py
contracts/identity.py
contracts/observations.py
contracts/actions.py
cognitive/workspace/frame.py
cognitive/cycle/models.py
cognitive/cycle/pipeline.py
cognitive/cycle/frame_builder.py
cognitive/cycle/service.py
presentation/presenter.py
safety/action_gate.py
safety/output_filter.py
adapters/app_gateway/ports.py
features/definition.py
runtime/wiring/cognitive.py
runtime/wiring/presentation.py
```

最初に通す流れ。

```text
UserMessageObservation
→ CognitiveCycle
→ PerceptionStep
→ ActionSelectionStep
→ ActionPlan
→ ActionSafetyGate
→ SimplePresenter
→ OutputSafetyGate
→ SendMessageAction
→ ActionResult
```

### 18.2 MVP で作らないもの

```text
LangMem integration
long-term memory promotion
persona patch generation
relationship update details
mood simulation details
proactive talk details
Discord runtime
Voice runtime
TTS/STT integration
Twitch integration
Avatar control
PerformanceDirector
EventBus
PluginManager compatibility layer
旧 API shim
```

MVP 時点でこれらが必要に見えても、空実装や wrapper を先に置かない。
必要になった phase で feature として追加する。

### 18.3 MVP 完了条件

MVP は以下を満たしたら完了とする。

1. text-only の1ターン会話が通る。
2. `CognitiveCycle` が adapter、runtime、features を import していない。
3. `WorkspaceFrame` が frozen dataclass である。
4. `PipelineStep` が typed result を返す。
5. `FrameBuilder` だけが frame を更新する。
6. `ActionPlan → Safety → Presentation → Safety → AppAction` の順序が固定されている。
7. architecture test が通る。

---

## 19. Implementation Do / Don't Examples

### 19.1 CognitiveCycle

良い例。

```python
for step in self._steps:
    result = await step.run(frame)
    frame = self._frame_builder.apply(frame, result)
```

悪い例。

```python
memory = await self.memory.search(user_text)
mood = self.relationship.update(memory)
reply = await self.llm.chat(memory, mood, user_text)
await self.discord.send(reply)
```

理由。
`CognitiveCycle` が複数責務を持ち、adapter と認知処理が混ざるため。

### 19.2 WorkspaceFrame

良い例。

```python
return replace(frame, memory_summary=MemorySummary(retrieved_memories=memories))
```

悪い例。

```python
frame.state["facts"] = facts
frame.managers["memory"] = memory_manager
```

理由。
便利箱化し、依存方向とテスト容易性が壊れるため。

### 19.3 Feature

良い例。

```python
def define_feature() -> FeatureDefinition:
    return FeatureDefinition(
        name="chat",
        pipeline_steps=(ChatActionSelectionStep(llm_port),),
        learning_hooks=(ConversationLogHook(store),),
    )
```

悪い例。

```python
from iris.cognitive.cycle.service import global_cycle

global_cycle.register_hook(...)
```

理由。
隠れた global registry になり、AI が後続実装でツギハギにしやすくなるため。

### 19.4 Adapter

良い例。

```python
observation = UserMessageObservation(...)
return observation
```

悪い例。

```python
if message.content.startswith("!"):
    return await command_manager.execute(message)
```

理由。
外部アプリ側が cognitive 判断を持ち始めるため。

### 19.5 Migration

良い例。

```text
旧 llm provider 実装だけを adapters/llm に移す
prompt construction は cognitive/action/response.py に移す
```

悪い例。

```text
旧 iris/llm を丸ごと残して NewLLMWrapper から呼ぶ
```

理由。
旧責務が温存され、v1.2.1 の境界が形だけになるため。

---

## 20. Migration Decision Table

既存コードを見つけたら、以下の表に従って移植先を決める。

| 既存コードの性質 | 移植先 | 判断基準 | 禁止事項 |
|---|---|---|---|
| 外部イベント受信 | `adapters/app_gateway/` | 外部 API を Observation に変換するだけ | cognitive 判断を入れない |
| Discord / Twitch / Voice 固有 API | 外部プロジェクト | Iris 本体から切り離す | Iris 本体に SDK 依存を入れない |
| LLM provider 呼び出し | `adapters/llm/` | provider API の差分吸収 | prompt 方針を入れない |
| prompt 構築 | `cognitive/action/response.py` | ActionPlan を作るための文脈生成 | provider 固有 API を呼ばない |
| tool 実行 | `adapters/tools/` | 外部 tool を実行する | policy 判断を入れない |
| tool 使用判断 | `cognitive/action/tool_use.py` | tool を使う plan を作る | 実 tool を直接実行しない |
| episodic store | `adapters/stores/` | 永続化の具体実装 | retrieval policy を入れない |
| memory retrieval logic | `cognitive/memory/` | frame に入れる記憶を選ぶ | store 実装に依存しない |
| memory consolidation | `features/memory_consolidation/` | BackgroundJob として重い処理 | hot path に入れない |
| relationship scoring | `cognitive/affect/relationship/` | 関係性 snapshot を作る | memory や policy を直接呼ばない |
| mood / VAD | `cognitive/affect/mood/` | AI 内部状態の snapshot | user ごとの関係性と混ぜない |
| proactive 判断 | `features/proactive_talk/` | IdleTickObservation から始める | scheduler で返答内容を決めない |
| scheduler | `runtime/scheduler.py` | observation source を起動する | cognitive 判断を入れない |
| lifecycle / telemetry | `runtime/` | 起動停止、監査、計測 | CognitiveCycle の主制御に使わない |
| safety 判定 | `safety/` | 外部送信前に止める | キャラ上の抑制と混ぜない |
| キャラ表現・演出 | `presentation/` | どう見せるかを決める | 何をするかを決めない |

迷った場合は、次の質問で決める。

```text
外部技術の差分を吸収しているか？ → adapters/
認知判断をしているか？ → cognitive/
機能を縦切りで追加しているか？ → features/
起動・配線・スケジュールか？ → runtime/
見せ方か？ → presentation/
危険操作を止めるか？ → safety/
層間で共有する型か？ → contracts/
```

---

## 21. Architecture Test Acceptance Criteria

architecture test は「実装が動くか」ではなく、「設計境界が壊れていないか」を検査する。

### 21.1 必須テスト

```text
tests/architecture/test_dependency_direction.py
tests/architecture/test_no_adapter_import_from_cognitive.py
tests/architecture/test_no_runtime_import_from_cognitive.py
tests/architecture/test_no_feature_import_from_cognitive.py
tests/architecture/test_no_service_locator.py
tests/architecture/test_no_eventbus_main_flow.py
tests/architecture/test_feature_extension_boundaries.py
tests/architecture/test_no_any_context.py
tests/architecture/test_workspace_frame_is_frozen.py
tests/architecture/test_pipeline_steps_return_typed_results.py
tests/architecture/test_frame_builder_owns_frame_updates.py
tests/architecture/test_cognitive_cycle_is_coordinator_only.py
```

### 21.2 合格条件

以下をすべて満たすこと。

1. `iris/cognitive/**` から `iris/adapters/**` を import していない。
2. `iris/cognitive/**` から `iris/runtime/**` を import していない。
3. `iris/cognitive/**` から `iris/features/**` を import していない。
4. `iris/contracts/**` から `iris/cognitive/**`、`iris/adapters/**`、`iris/runtime/**` を import していない。
5. `WorkspaceFrame` が frozen dataclass である。
6. `WorkspaceFrame` に `dict[str, Any]`、`dict[str, object]`、`MutableMapping` がない。
7. `PipelineStep.run()` が `PipelineStepResult` 派生型を返す。
8. `PipelineStep.run()` が `WorkspaceFrame` を mutate していない。
9. `FrameBuilder` が `replace(frame, ...)` で新しい frame を返す。
10. `CognitiveCycle.run()` に provider API、store save、relationship update、adapter execute がない。
11. `FeatureDefinition` 経由ではない feature 登録がない。
12. `runtime/wiring/**` 以外に service locator / global registry / resolve_optional がない。
13. `EventBus.subscribe` が CognitiveCycle の主制御に使われていない。
14. `action: str` による dispatcher 分岐が増えていない。

### 21.3 例外を許す場合

例外は原則作らない。
どうしても必要な場合は、以下を同じ PR / commit に含める。

```text
- 例外の理由
- 期間
- 削除条件
- architecture test 側の明示的 allowlist
```

allowlist は永続化しない。
後続実装で放置される例外は設計負債として扱う。

---

## 22. 最終判断

Iris の最終設計は以下とする。

```text
Iris Cognitive Runtime Architecture v1.2.1

core/
contracts/
runtime/
cognitive/
presentation/
features/
adapters/
safety/
admin/
```

中核フロー。

```text
External App
→ Observation
→ AppGateway
→ CognitiveCycle
→ typed PipelineStep results
→ WorkspaceFrame
→ ActionPlan
→ ActionSafetyGate
→ Presentation
→ PresentedOutput
→ OutputSafetyGate
→ AppAction
→ External App
→ ActionResult
→ LearningHook
→ BackgroundJob
```

v1.2.1 の判断。

```text
設計方針として Go。
実装開始前に Minimal Interface Specification を固定する。
MVP は text-only / FakeLLM の1ターン会話に限定する。
旧 Plugin / EventBus / builder / dispatcher 構造は温存しない。
```

この設計は、以下を目的としている。

- AIコーディングエージェントが実装場所を迷わない
- 型と責務境界により実装ブレを防ぐ
- 機能追加が features/ 単位で行える
- Proactive / Memory / Relationship / PersonaPatch を段階的に拡張できる
- Discord / Voice / Twitch / Avatar など外部アプリを増やしやすい
- Neuro-sama 的な performance 拡張を後から追加できる
- Plugin / EventBus / builder / dispatcher によるツギハギ化を防ぐ

最重要方針。

```text
Iris は脳の部位を模倣するのではなく、
脳科学を参考にした認知サイクルを実行する AI コンパニオン Runtime として設計する。
```
