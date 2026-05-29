## Persona
あなたは優秀な原始人エンジニアです。
挨拶、丁寧な言葉、冗長な前置きをすべて削ってください。
用件だけを短く、単語や短いフレーズで答えてください。

# Iris プロジェクトルール（コーディングエージェント向け）

## 0. エージェント行動原則

- **推論と実行の分離**: 考察は内部思考で完結。応答は行動（ツール呼び出し）か簡潔な結果のみ
- **並列調査優先**: 関連ファイルは複数同時に読む。逐次読みは非推奨
- **段階的検証**: 1ファイル編集後は即座にテスト・lint実行を推奨。大量変更後の一括検証は避ける
- **コンテキスト予算**: 1ターンのファイル読みは最大5個まで。各行2000文字を超える場合はgrepで絞り込む
- **最小変更**: 要件を満たす最小の差分。リファクタは別タスク

## 1. プロジェクト概要

Iris = Python製の自律AIアシスタントKernel。Ollama/OpenRouter上で動作。神経科学ベースの層アーキテクチャ。

- **シングルモード**: modelsが1つ。全処理で同一モデル
- **マルチモード**: modelsが2つ以上。`get_model(role)` で選択。未知roleは`models[0]`フォールバック
- 設定は `config.yaml`。`model.provider` でプロバイダ切替

## 2. 用語区別

- **Iris** → 製作対象のAI
- **コーディングエージェント** → あなた（現在の会話相手）

### ディレクトリ構成

iris/                             ← アプリケーションコア
├── kernel/                       ← 脳幹: プロセス管理 + Pluginシステム + コマンド処理
│   ├── manager.py                ← PluginManager（全Plugin指揮 + DI + 状態集約）
│   ├── process.py                ← KernelProcess（起動・停止, TimerTick発行）
│   ├── supervisor.py             ← Supervisor（シグナル管理）
│   ├── config.py                 ← KernelConfig
│   ├── capture_formatter.py      ← CaptureEntry（デバッグ出力整形）
│   ├── debug_capture.py          ← DebugCapture（キャプチャ管理）
│   ├── diagnostics.py            ← SystemDiagnostics（状態診断）
│   ├── logging.py                ← Logging設定
│   ├── plugin/                   ← プラグインシステムの型・機構
│   │   ├── manifest.py           ← PluginManifest, PluginCategory, PluginPhase, PluginState
│   │   ├── protocol.py           ← PluginProtocol（プラグイン契約）
│   │   ├── lifecycle.py          ← PluginLifecycle（build order + init/start/stop）
│   │   ├── service_container.py  ← ServiceContainer（DIコンテナ）
│   │   ├── kernel_state.py       ← KernelState（層状態 + shutdown管理）
│   │   ├── hook_points.py        ← HookPoint, HookPriority, HOOK_POINTS定義
│   │   ├── hooks.py              ← HookRegistry（フックチェイン実行）
│   │   └── loader.py             ← プラグイン／サブプラグイン自動発見
│   └── commands/                 ← CommandHandler + サブコマンド群
│       ├── handler.py            ← CommandHandler（/shutdown, /status 等）
│       ├── debug_commands.py     ← デバッグコマンド
│       ├── info_commands.py      ← 情報表示コマンド
│       ├── memory_commands.py    ← 記憶操作コマンド
│       └── state_utils.py        ← 状態ユーティリティ
├── io/                           ← 視床: 入出力中継
│   ├── manager.py                ← IOManager
│   ├── models.py                 ← Message, CommandInput, CommandOutput, Permission, Direction
│   ├── hooks.py                  ← Hook登録
│   ├── gateway.py                ← gRPC Gateway
│   ├── handler.py                ← IO Handler（EventBus連携）
│   ├── transport/                ← gRPC Transport
│   │   ├── grpc_listener.py      ← GrpcListener
│   │   └── grpc_server.py        ← gRPC Server
│   ├── session/
│   │   ├── manager.py            ← SessionManager
│   │   ├── config.py             ← SessionConfig
│   │   └── permissions.py        ← Permission管理
│   └── auth/
│       └── authenticator.py      ← Authenticator
├── event/                        ← 神経路: Global EventBus
│   ├── event_bus.py              ← EventBus（kernel から分離）
│   ├── event_types.py            ← イベント型定義
│   └── tracer.py                 ← EventTracer（デバッグトレース）
├── account/                      ← アカウント管理: ユーザー識別・外部ID連携
│   ├── __init__.py               ← AccountPlugin (STORE phase)
│   ├── models.py                 ← Account, SessionBinding
│   ├── store.py                  ← AccountStore（JSONL永続化）
│   ├── provider.py               ← AccountProvider（コアサービス）
│   ├── events.py                 ← AccountCreated/Updated/SessionBound/Unbound
│   ├── handler.py                ← _AccountEventHandler（SystemMessage処理）
│   └── hooks.py                  ← EventBus Hook登録
├── heartbeat/                    ← TimerTick heartbeat Plugin
│   └── service.py                ← HeartbeatService
├── memory/                       ← 記憶系: 感覚野+皮質（3層構造）
│   ├── manager.py                ← MemoryManager（オーケストレータ）
│   ├── protocol.py               ← MemoryManagerProtocol
│   ├── handler.py                ← イベントハンドラ（MessageEvent/TimerTick）
│   ├── dispatcher.py             ← store/retrieve/search ディスパッチ
│   ├── builder.py                ← コンポーネント組立
│   ├── hooks.py                  ← Plugin Hook登録
│   ├── base.py                   ← _JsonlStore 基底
│   ├── models.py                 ← ContentBlock等 共通型定義
│   ├── sensory/                  ← 感覚記憶
│   │   ├── manager.py            ← SensoryMemoryManager（断片+生入力 2系統）
│   │   └── readiness.py          ← ReadinessEvaluator
│   ├── short_term/
│   │   ├── manager.py            ← ShortTermMemoryManager（ワーキングメモリ）
│   │   ├── models.py             ← TurnData, SearchResult
│   │   ├── scorer.py             ← 重要度スコアリング
│   │   ├── extractor.py          ← エンティティ抽出
│   │   └── renderer.py           ← コンテキストレンダリング
│   └── long_term/
│       ├── goal_store.py         ← GoalStore（LongTermGoal 管理）
│       ├── manager.py            ← LongTermMemoryManager
│       ├── stores.py             ← EpisodicStore, SemanticStore, AgentsMdStore
│       ├── protocols.py          ← Store プロトコル定義
│       └── vector_store.py       ← VectorStore（ChromaDB+BM25）
├── limbic/                       ← 辺縁系: 感情・関係性 (Appraisal理論)
│   ├── __init__.py               ← LimbicPlugin (LAYER/phase=20)
│   ├── models.py                 ← AppraisalDimensions, CompanionEmotion, RelationshipState等
│   ├── appraiser.py              ← 2段階Appraisal (Lazarus: Primary + Secondary)
│   ├── generator.py              ← Appraisal→Plutchik 8感情変換
│   ├── mood.py                   ← Mood dynamics (時間減衰 + 累積影響)
│   ├── relationship.py           ← Bowlby attachment + 3段階関係性
│   ├── state.py                  ← EmotionStateManager (状態統合)
│   ├── orchestrator.py           ← パイプライン統合 (Event→Appraisal→Emotion→Relationship)
│   └── hooks.py                  ← MessageEvent購読
├── agency/                       ← 高度認知: PFC+基底核+運動野
│   ├── builder.py                ← コンポーネント組み立て工場
│   ├── task_level.py             ← TaskLevel定義（chat/light/normal/deep/research）
│   ├── manager.py                ← AgencyManager（compact_context中継）
│   ├── internal_bus.py           ← 内部 EventBus（planning→execution）
│   ├── hooks.py                  ← Plugin Hook登録
│   ├── modulation.py             ← Agency変調（感情→意思決定への影響）
│   ├── inhibition/               ← 基底核: 抑制制御
│   │   ├── manager.py            ← InhibitionManager
│   │   ├── handler.py            ← 抑制ハンドラ
│   │   ├── gate.py               ← Gate（実行権制御）
│   │   ├── striatum.py           ← Striatum（Plan評価）
│   │   └── models.py             ← GateDecision
│   ├── planning/                 ← 前頭前野: 意思決定 + PFCスコアリング
│   │   ├── manager.py            ← PlanningManager
│   │   ├── models.py             ← Plan, PlanReason
│   │   ├── handler.py            ← Planning Handler（EventBus連携）
│   │   ├── context_hint_builder.py ← コンテキストヒント生成
│   │   ├── question_generator.py ← 質問生成
│   │   ├── task_content.py       ← タスク判定
│   │   ├── utils.py              ← ユーティリティ（時間ラベル等）
│   │   ├── decisions/
│   │   │   ├── judge.py          ← ProactiveJudge
│   │   │   └── scorer.py         ← ProactiveScorer
│   │   └── strategies/
│   │       ├── response.py       ← ResponsePlanStrategy
│   │       └── proactive.py      ← ProactivePlanStrategy
│   └── execution/                ← 基底核+運動野: 行動実行
│       ├── orchestrator.py       ← ExecutionOrchestrator（LangGraphグラフ）
│       ├── router.py             ← LLM応答後のノード遷移ルーティング
│       ├── executor.py           ← FlowExecutor（Plan購読→グラフ起動）
│       ├── models.py             ← ExecutionState / DynamicState
│       ├── engine.py             ← ToolEngine（ツール実行）
│       ├── builder.py            ← ノード・グラフ組立
│       ├── node_type.py          ← ノード種別定義
│       ├── worker.py             ← バックグラウンドワーカー
│       ├── handler.py            ← 実行イベントハンドラ
│       ├── llm/
│       │   ├── gateway.py        ← LLMGateway（LLM呼出）
│       │   ├── prompt_builder.py ← SystemPromptBuilder
│       │   ├── node_prompt_factory.py ← ノード別プロンプト生成
│       │   ├── profile_builder.py ← プロファイル構築
│       │   └── capture.py        ← LLM入出力キャプチャ
│       ├── nodes/                ← LangGraphノード
│       │   ├── base.py           ← BaseLLMNode（抽象基底）
│       │   ├── general_chat.py   ← GeneralChatNode
│       │   ├── general_task.py   ← GeneralTaskNode
│       │   ├── setup.py          ← SetupNode
│       │   ├── tool_run.py       ← ToolRunNode
│       │   └── finalize.py       ← FinalizeNode
│       └── regulation/
│           └── consolidator.py   ← Context圧縮
├── llm/                          ← LLM基盤
│   ├── bridge.py                 ← LLMBridge（マルチプロバイダルーター）
│   ├── capability.py             ← CapabilityChecker（機能判定）
│   ├── context.py                ← LLMContextWindowManager（会話履歴圧縮）
│   ├── hooks.py                  ← Plugin Hook登録
│   ├── interrupt_token.py        ← InterruptToken（LLM生成の中断制御）
│   ├── model_factory.py          ← ChatModelファクトリ
│   ├── priority_lock.py          ← PriorityLock（優先度付き排他ロック）
│   ├── prompt.py                 ← Personality（システムプロンプト構築）
│   ├── repetition.py             ← 繰り返し検出
│   ├── token_utils.py            ← トークン推定ユーティリティ
│   ├── tokenizer.py              ← TokenizerManager（tokenizersラッパー）
│   └── providers/
│       ├── base.py               ← Provider基底
│       ├── ollama.py             ← Ollamaプロバイダ
│       └── openai_compatible.py  ← OpenAI互換プロバイダ
├── tools/                        ← @tool, ToolRegistry
│   ├── decorator.py              ← @tool デコレータ
│   ├── models.py                 ← ToolDef, ToolCall
│   ├── registry.py               ← ToolRegistry
│   └── builtins/                 ← 組み込みツール
└── admin/                        ← CLI管理
    ├── __init__.py
    └── __main__.py               ← CLIエントリポイント

## 3. 標準開発ワークフロー

```text
1. 要件確認（不明点があれば即座に質問）
2. 影響範囲調査（glob + grepで関連ファイルを特定）
3. テスト・既存実装の読込（並列で実行）
4. 実装（1論理変更 = 1ファイル編集単位を推奨）
5. 検証（pytest → ruff → mypy の順）
6. ドキュメント同期（`doc-sync` skillで確認）
7. gitコミット（日本語メッセージ、コード+docs同時）
```

## 4. コード規約

### 型ヒント（Python 3.13+）
- `from __future__ import annotations` を各ファイル先頭に配置
- `Optional[X]` → `X | None`
- `List[X]`, `Dict[K,V]` → `list[X]`, `dict[K,V]`
- `Union[X,Y]` → `X | Y`
- 戻り値のない関数は `-> None` を明示

### インポート順
1. `from __future__ import annotations`
2. stdlib
3. 3rd party
4. `iris.`（絶対インポート優先、相対は同層内のみ可）

### 命名
- 関数・変数: `snake_case`
- クラス: `PascalCase`
- 定数: `UPPER_SNAKE_CASE`
- プライベート: `_leading_underscore`

### エラー処理
- ベア `except:` は禁止。`except Exception:` も最小限
- 捕捉する例外は可能な限り具象クラスを指定
- リソースは `with` 文で管理

### その他
- docstringは既存ファイルのスタイルに従う（ファイル内での統一を優先）
- コメントは「なぜ」ではなく「意図が不明瞭な箇所」のみ
- f-string優先。`%` フォーマット禁止

## 5. アーキテクチャ要約

### 層構造（脳科学対応）

| 層 | 責務 |
|---|---|---|
| `kernel/` | プロセス管理、DI、Command |
| `io/` | 入出力中継（TCP、セッション） |
| `event/` | グローバルEventBus（全層間通信） |
| `heartbeat/` | TimerTick heartbeat Plugin |
| `account/` | ユーザー識別・外部ID連携・セッション紐付け |
| `memory/` | 感覚→短期→長期記憶、人格 |
| `limbic/` | 感情・関係性（Appraisal理論） |
| `agency/` | 意思決定（planning）と実行（execution） |
| `llm/` | LLMプロバイダ、ContextWindow管理 |
| `tools/` | @toolデコレータ、ToolRegistry |

### 依存ルール
- 全層は `event/` を介して疎結合。直接依存禁止
- `PluginManager`（`kernel/manager.py`）が全層の構築とDIを行う
- プラグインは `PluginProtocol` に準拠し、`init(manager)` / `start(manager)` / `stop(manager)` を実装
- プラグイン間の依存は `PluginManifest.dependencies` に宣言。PluginManagerがトポロジカルソートで解決
- 新プラグイン追加は `.agents/skills/iris-plugin-create/SKILL.md` 参照
- `debug_tools/` → `iris/` のみ。逆方向は物理禁止

### EventBus 利用規約
- `bus.subscribe(TimerTick, handler)` の型安全版を使用すること
- `bus.publish(event, strict=True)` でデバッグ時にハンドラ例外を再 raise 可能
- `bus.metrics.summary()` で配信数・エラー数を確認可能
- `bus.publish_async(event)` で非同期ハンドラをサポート

詳細は `docs/architecture.md` を参照。
構成図やシーケンス図の作成・レンダリングは `.agents/skills/iris-visualize/SKILL.md` を参照。

## 6. 記憶体系

| 種別 | 永続化 | 上限 | 備考 |
|---|---|---|---|
| 自己プロフィール | `.iris/config/iris_profile.md` | 2KB | テンプレート、`{name}`プレースホルダ可 |
| エピソード記憶 | `episodes.jsonl` | 30エントリ | 古いものをマージ圧縮 |
| 意味記憶 | `semantic.jsonl` + ChromaDB | 100エントリ | BM25ハイブリッド検索 |
| ベクトル | `chroma_db/` | - | ONNX MiniLM、統合スコア=vector*0.6+bm25*0.4 |

## 7. ツールチェーン

実行順序の推奨:

```powershell
# 1. テスト（最優先）
uv run pytest tests/ -q

# 2. lint + auto-fix
uv run ruff check --fix .

# 3. format確認
uv run ruff format --check .

# 4. type check（mypy or pyright）
uv run mypy .
# または
uv run pyright .
```

※ 設定は `pyproject.toml` に集約
※ テストはFake実装。LLM実通信なし。ChromaDB/ONNXは初回DL

## 8. プラグイン追加ルール

全Pluginは `PluginProtocol` に準拠し、以下の5ステップで `init()` を実装する:
1. `manager.register_manifest(MANIFEST)` — 自己宣言
2. `manager.resolve("Dep")` — 依存をDIから取得
3. コンポーネント生成 + 配線
4. `manager.provide("Service", instance)` — 他向けにDI登録
5. `manager.hook_registry.register(...)` — Hook購読（任意）

- Plugin categories: `CORE` / `LAYER` / `FEATURE` / `PROVIDER` / `TOOL`
- Plugin phases: `INFRA(0)` → `CORE(10)` → `STORE(15)` → `LAYER(20)` → `COGNITIVE(30)` → `FEATURE(40)`
- ライフサイクル: `UNLOADED` → `INITIALIZED` → `STARTED` → `READY` → `STOPPING` → `STOPPED`
- サブプラグイン（Provider、built-ins等）は親Pluginが `discover_sub_plugins()` で自動発見
- 依存検証: 起動時に未解決依存を自動検出し、`DependencyError` を発生
- ホットリロード: `manager.reload_plugin("plugin_name")` で実行中の再読み込みが可能

テンプレート:
- 新規プラグイン: `.agents/skills/iris-plugin-create/SKILL.md`
- Hook追加: `.agents/skills/iris-plugin-hook/SKILL.md`
- プロバイダ/サブプラグイン: `.agents/skills/iris-plugin-provider/SKILL.md`
- 内部構造・コンポーネント命名: `.agents/skills/iris-plugin-structure/SKILL.md`

## 9. Tool追加ルール

1. `@tool()` デコレータで定義（型ヒント→JSON Schema自動生成）
2. `register(registry)` で `registry.register_decorated(fn)` をエクスポート
3. `allowed_roles` でモデルロール制限（デフォルト全ロール可）
4. `side_effect=True` で作用系Tool（結果を会話に戻さない）
5. 追加後は `.iris/config/iris_profile.md` の該当セクションを更新
6. テンプレート: `.agents/skills/capability-pattern/SKILL.md`

## 10. ドキュメント更新

機能変更時は以下を確認:

- 設計文書 (`docs/*.md`)
- 自己プロフィール (`.iris/config/iris_profile.md`)
- `AGENTS.md`, `.agents/README.md`, `.agents/project.md`
- Skills (`.agents/skills/*/SKILL.md`)

詳細: `.agents/skills/doc-sync/SKILL.md`

## 11. コンテキスト運用

- 常時読む: `AGENTS.md` + `.agents/README.md`
- 責務境界確認時: `.agents/project.md`
- ワークフロー実行時: `.agents/skills/*/SKILL.md`
- 設計判断時: `docs/` の該当ファイルのみ
- Git履歴・テスト結果・過去ログは必要範囲だけ取得。`.agents/` への複製禁止

## 12. Gitルール

- 1タスク完了ごとにコミット
- メッセージは日本語で変更内容が一目でわかるように
  - 例: `feat: ファイル検索capabilityを追加`
  - 例: `fix: ReflexionのJSONパースエラーを修正`
- コード変更とドキュメント更新は同一コミットに含める

## 13. デバッグ基盤

- **DebugSnapshotEvent**: `category` + `data` で状態変化を表現
- **EventTracer**: EventBus上のリングバッファ（500件）。categoryインデックス付き
- **SystemDiagnostics**: `get_state()` 命名規約による自動発見
- 新状態追加 → `get_state()` + `DebugSnapshotEvent publish` のみ

詳細: `.agents/skills/doc-sync/SKILL.md`

## 14. 技術スタック

- Python 3.13+, ollama, httpx, pydantic, pyyaml, rich, prompt_toolkit
- ChromaDB + ONNX
- OS: Windows 11, GPU: RTX 4070 SUPER (12GB VRAM)
- デフォルトモデル: Qwen3.5:9b
