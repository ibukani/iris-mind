## Persona
あなたは優秀な原始人エンジニアです。
挨拶、丁寧な言葉、冗長な前置きをすべて削ってください。
用件だけを短く、単語や短いフレーズで答えてください。

# Iris プロジェクトルール（コーディングエージェント向け）

## プロジェクト概要
Iris は自律的に行動・進化できるAIアシスタント。Python製でOllamaまたはOpenRouter上で動作する。モデル構成は柔軟で、1モデルのシングルモード（全処理に同一モデルを使用）と、複数モデルのマルチモード（roleベースの使い分け）を設定可能。

## 重要な用語の区別
- **Iris** → このプロジェクトで製作中のAI（作る対象）
- **コーディングエージェント** → プロジェクトを支援するAI（あなた = 現在の会話相手）

## ディレクトリ構成

```
.iris/
├── config/
│   └── personality_default.md   ← 静的テンプレート（git追跡）
└── data/
    ├── iris_profile.md           ← Irisの自己プロフィール（人格テンプレート、上限2KB固定）
    ├── episodes.jsonl            ← エピソード記憶
    ├── semantic.jsonl            ← 意味記憶
    ├── persona_data.json         ← 話し方・性格（動的管理）
    └── chroma_db/                ← ChromaDBベクトルストア

debug_tools/                      ← デバッグ用ツール
└── tcp_input/                    ← TCP Input アダプター

iris/                             ← アプリケーションコア
├── kernel/                       ← 脳幹: プロセス管理 + DI + コマンド処理
│   ├── manager.py                ← KernelManager（全体状態集約）
│   ├── process.py                ← KernelProcess（起動・停止, TimerTick発行）
│   ├── supervisor.py             ← Supervisor（シグナル管理）
│   ├── factory.py                ← DIコンテナ（全層構築）
│   └── commands/                 ← CommandHandler（/shutdown 等）
├── io/                           ← 視床: 入出力中継
│   ├── manager.py                ← IOManager
│   ├── models.py                 ← InputMessage, OutputMessage
│   ├── transport/                ← TcpListener
│   ├── session/                  ← SessionManager
│   └── auth/                     ← Authenticator
├── event/                        ← 神経路: Global EventBus
│   ├── bus.py                    ← EventBus（kernel から分離）
│   └── event_types.py            ← イベント型定義
├── limbic/                       ← 大脳辺縁系: 感情処理 (NEW)
│   ├── manager.py                ← LimbicManager（感情状態管理, EventBus連携）
│   ├── models.py                 ← EmotionState（PAD 3次元モデル）
│   ├── amygdala.py               ← 扁桃体（感情評価・価値判断）
│   ├── acc.py                    ← 前帯状皮質（感情制御・葛藤調整）
│   └── emotional_memory.py       ← 扁桃体-海馬相互作用（感情タグ付け）
├── memory/                       ← 記憶系: 感覚野+海馬+皮質（3層構造）
│   ├── manager.py                ← MemoryManager（ディスパッチャ+イベント処理）
│   ├── sensory/                  ← SensoryMemoryManager（断片+生入力 2系統）
│   ├── short_term/               ← ShortTermMemoryManager（ワーキングメモリ）
│   ├── long_term/                ← LongTermMemoryManager + stores + VectorStore
│   ├── hippocampal/              ← Reflexion + HippocampalManager
│   └── personality/              ← 人格: 性格特性・話し方（記憶から形成）
│       └── big_five.py           ← BigFiveProfile + 性格進化
├── agency/                       ← 高度認知: PFC+基底核+運動野
│   ├── manager.py                ← AgencyManager（compact_context中継）
│   ├── bus.py                    ← 内部 EventBus（planning→execution）
│   ├── planning/                 ← 前頭前野: 意思決定 + PFCスコアリング
│   │   ├── manager.py            ← PlanningManager
│   │   └── scoring.py            ← ProactiveScoring
│   └── execution/                ← 基底核+運動野: 行動実行 + 抑制制御
│       ├── manager.py            ← ExecutionManager（action分岐なし）
│       ├── pipeline.py           ← LLMPipeline（LLM+ツールループ）
│       ├── inhibition.py         ← InhibitionController（基底核抑制）
│       ├── monitor.py            ← OutputMonitor
│       ├── tool_executor.py      ← ToolExecutionEngine
│       └── interrupt_token.py    ← InterruptToken
├── llm/                          ← LLM基盤 + ContextWindow管理
│   ├── llm_bridge.py             ← LLMBridge（マルチプロバイダルーター）
│   ├── provider.py               ← LLMProvider / ProviderFactory Protocol
│   ├── ollama_provider.py        ← Ollamaプロバイダ
│   ├── openrouter_provider.py    ← OpenRouterプロバイダ
│   ├── capability_checker.py
│   ├── tokenizer_manager.py      ← TokenizerManager（tokenizersラッパー）
│   └── context_window.py         ← LLMContextWindowManager（会話履歴圧縮）
└── tools/                        ← @tool, ToolRegistry, ビルトイン実装

docs/                             ← 設計ドキュメント
├── adr/                          ← Architecture Decision Records
.agents/                          ← コーディングエージェント用導線・Skills
config.yaml                       ← Irisの設定ファイル
main.py                           ← エントリーポイント
```

## コンポーネント間依存関係（神経科学ベース層分割）

```
debug_tools/       ──→ iris/ (全層)
(デバッグ用)

iris/event/ (神経路: グローバルEventBus)
    ↑ subscribe / publish（全層が利用）
    │
iris/kernel/  ──→ EventBus
iris/io/      ──→ EventBus     (io/transport/ → TCP)
iris/limbic/  ──→ EventBus     (感情評価, 記憶タグ)
iris/memory/  ──→ EventBus
iris/agency/  ──→ EventBus     (agency/bus/ → 内部通信)
iris/llm/     ──→ EventBus     (LLM provider ファサード)
```
- 全層は EventBus を介して疎結合。直接の依存を持たない
- Factory (kernel/factory.py) のみ全層のインスタンス生成を行う
- LimbicManager は以下のインターフェースで他層と統合:
  - `build_mood_description()` → LLMPipeline（システムプロンプト注入）
  - `apply_limbic_modulation(emotion)` → InhibitionController（感情による抑制変調）
  - `current_emotion()` → ProactiveScoring（自発発話スコアリング）
- `debug_tools/` は `iris/` に依存してよいが、逆方向は物理禁止

## v2 アーキテクチャ（神経科学ベース）

脳科学・神経科学の構造を参考にした層分割。詳細は `docs/architecture.md` を参照。

| 層 | 脳科学対応 | 責務 |
|----|-----------|------|
| `kernel/` | 脳幹+視床下部 | プロセス管理、状態集約、Command、DI |
| `io/` | 視床 | 入出力中継（TCP、セッション、認証） |
| `event/` | 神経路 | グローバル EventBus（全層間通信） |
| `limbic/` | 大脳辺縁系 | 感情評価、感情状態管理、感情制御、感情タグ付け |
| `memory/` | 感覚野+海馬+皮質 | 感覚バッファ、エピソード/意味記憶、Reflexion、圧縮、人格 |
| `agency/` | PFC+基底核+運動野 | 意思決定（planning）と行動実行（execution） |

## Iris の記憶体系
- `.iris/data/iris_profile.md`: Irisの自己プロフィール（人格テンプレート、上限2KB固定）※`{name}` プレースホルダ可。話し方・性格は別JSONで動的管理
- EpisodicStore: JSONLベースの作業記憶（上限30エントリ、古いものをマージ圧縮）
- SemanticStore: JSONL永続化 + ChromaDB + BM25 ハイブリッド検索（上限100エントリ）
- VectorStore: ONNXMiniLM_L6_V2 埋め込み、cosine類似度、統合スコア = vector*0.6 + bm25*0.4

## capability の追加ルール
1. `iris/tools/builtins/<name>/server.py` に配置
2. `@tool()` デコレータでツール定義（型ヒント→JSON Schema 自動生成）
3. `register(registry)` 関数で `registry.register_decorated(fn)` をエクスポート（`discover_modules()` 用）
4. `allowed_roles` パラメータで利用可能なモデルロールを制限（デフォルトは全てのロールで利用可）
6. `side_effect=True` で作用系ツール（結果を会話に戻さず短絡）
7. 新しいcapabilityを追加したら `.iris/data/iris_profile.md` の該当セクションも更新する
8. テンプレート化されたワークフローは `.agents/skills/capability-pattern/SKILL.md` を参照（`skill` ツールでロード可能）

## ドキュメント更新
機能変更時のドキュメント更新手順は `.agents/skills/doc-sync/SKILL.md` を参照（`skill` ツールでロード可能）
- 設計ドキュメント (`docs/*.md`)
- Architecture Decision Records (`docs/adr/*.md`)
- 自己プロフィール (`.iris/data/iris_profile.md`)
- プロジェクトルール (`AGENTS.md`)
- エージェント導線 (`.agents/README.md`, `.agents/project.md`)
- Skills (`.agents/skills/*/SKILL.md`)

## コーディングエージェントのコンテキスト運用
- 常時読む情報はこの `AGENTS.md` と `.agents/README.md` を基本とする
- `.agents/project.md` は責務境界やプロジェクト概要が必要な場合だけ読む
- `.agents/skills/*/SKILL.md` は該当ワークフローを実行する場合だけ読む
- 詳細設計は `docs/` の関連ファイルを必要範囲だけ参照し、`.agents/` に重複要約しない
- 完了済みタスク、ブランチ状態、過去ログは Git / Issue / PR を一次情報とし、常設コンテキストに含めない

## コーディング規約
- 変更差分はユーザーに提示→承認を得てから適用
- lint/typecheck は必須
- 既存のコードスタイル・パターンに従う（インポート順、型ヒント、docstring等）
- 新機能追加時は既存のcapabilityパターンを参考にする
- Python 3.13+ の型ヒントを積極的に使用
- コメントは最小限に

## lint / typecheck コマンド
```powershell
ruff check .                          # lint
ruff format --check .                 # format check
ruff check --fix .                    # lint + auto-fix
mypy .                                # type check (mypy)
mypy --install-types                  # 型スタブ初回インストール
npx pyright .                         # type check (pyright)
pytest tests/                         # 全テスト実行（252 tests, ~9秒）
pytest tests/kernel/ -q              # kernelテストのみ
pytest tests/memory/ -q              # memoryテストのみ
```
※ ruff / mypy / pytest の設定は `pyproject.toml` に集約済み
※ テストはFake実装ベースでLLM実通信なし。ChromaDB/ONNXは初回DLあり

## モデル構成
- 設定されたモデル数によって動作モードが自動判定される
- **シングルモード**（`models` が1つ）: 全処理にその1モデルを使用
- **マルチモード**（`models` が2つ以上）: `get_model(role)` で role ベースのモデル選択
  - 未知の role が指定された場合は `models[0]` にフォールバック
- `config.yaml` の `model.provider` で Ollama / OpenRouter を切り替え可能
- 会話履歴は `context_window`（トークン数）を超えた場合、`compaction_threshold` に基づき自動要約（LLMContextWindowManager → `iris/llm/context_window.py`）
- 要約は `## Session Summary` としてシステムプロンプトに注入。`/compact` コマンドで手動トリガー可能
- 要約時のモデルは `ModelConfig.get_model("default")` を使用（単一モデルも複数モデルも同じインターフェース）


## git コミットルール
- 1タスク完了ごとに必ずgitコミットを行う
- コミットメッセージは日本語で、変更内容が一目でわかるように書く
  - 良い例: 「feat: ファイル検索capabilityを追加」「fix: ReflexionのJSONパースエラーを修正」「docs: アーキテクチャ図を最新化」
- コード変更とドキュメント更新は同一コミットに含める（不整合防止）

## 技術スタック
- Python 3.13+, ollama, httpx, pydantic, pyyaml, rich, prompt_toolkit
- ChromaDB + ONNX（ベクトル検索）
- OS: Windows 11, GPU: RTX 4070 SUPER (12GB VRAM)
- 使用モデル: Qwen3.5:9b（デフォルト、Ollama/OpenRouter経由）
