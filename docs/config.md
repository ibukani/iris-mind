# Config 設計仕様

## 概要

Iris の設定は Pydantic BaseModel で構成される。`config.yaml` から読み込み、型バリデーションを自動実行する。

## Config ツリー

```
Config
├── model: ModelConfig          — LLMモデル関連
├── personality: PersonalityConfig — 人格・プロンプト
├── memory: MemoryConfig        — 記憶管理
├── proactive: ProactiveConfig  — 自発発話
├── session: SessionConfig      — セッション・通信
└── logging: LoggingConfig      — ログ出力
```

## ModelConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| models | list[ModelEntry] | qwen3.5:9b (default) | 使用モデル一覧 |
| provider | str | "ollama" | プロバイダ種別（"ollama" or "openrouter"） |
| base_url | str | "http://localhost:11434" | API URL（Ollama or OpenRouter） |
| api_key | str | "" | OpenRouter APIキー（${VAR_NAME}形式対応） |
| temperature | float | 0.7 | LLM生成温度 |
| num_gpu | int | 99 | GPUレイヤー数（99=全レイヤー、Ollamaのみ） |
| num_ctx | int | 8192 | コンテキスト長 |
| context_window | int | 0 | 会話ウィンドウサイズ（0=無制限） |
| compaction_threshold | float | 0.85 | 要約発動閾値（比率） |

**ModelEntry**:

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| name | str | — | モデル名（Ollamaタグ形式 or OpenRouterモデルスラッグ） |
| roles | list[str] | ["default"] | このモデルが担うロール一覧 |
| max_tokens | int | 512 | 最大出力トークン数 |
| temperature | float \| None | None | モデル個別の温度設定（上書き用） |
| num_ctx | int \| None | None | モデル個別のコンテキスト長（上書き用） |
| context_window | int \| None | None | モデル個別の会話ウィンドウ（上書き用） |
| capabilities | list[str] \| None | None | モデルの機能ラベル（例: ["vision", "tools"]） |
| performance_tier | str | "balanced" | 性能区分（"fast" / "balanced" / "capable"） |

- `roles` は YAML上で1要素なら文字列でも記述可能: `roles: default`
- モデルが1つだけの場合はシングルモードとなり、全処理にそのモデルを使用
- 複数モデルがある場合は `get_model(role)` で role に合致するモデルを選択
- `ModelEntry.role`（旧形式）の単一文字列は自動的にリストに変換される

**ModelConfig ヘルパーメソッド**:

| メソッド | 戻り値 | 説明 |
|---------|--------|------|
| `model_names` | list[str] | 全モデル名一覧（property） |
| `get_model(role)` | str | 指定 role に合致するモデル名。未合致時は models[0] にフォールバック |
| `get_effective_temperature(role)` | float | role 別実効温度。モデル個別設定がなければ ModelConfig.temperature |
| `get_effective_num_ctx(role)` | int | role 別実効コンテキスト長。モデル個別設定がなければ ModelConfig.num_ctx |
| `get_model_capabilities(role)` | list[str] | role 別の機能ラベル一覧 |
| `get_model_performance_tier(role)` | str | role 別の性能区分 |

## ProactiveConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| enabled | bool | False | 自発発話機能の有効/無効 |
| check_interval_sec | float | 5.0 | TimerTick 間隔（秒） |
| min_interval_sec | float | 30.0 | 自発発話の最小間隔 |
| max_interval_sec | float | 300.0 | 自発発話の最大間隔（時間スコア飽和） |
| tier1_auto_approve | bool | True | Tier1 自動許可の有効/無効 |
| tier2_confidence_threshold | float | 0.75 | Tier2 信頼度閾値 |
| tier2_cooldown_sec | float | 60.0 | Tier2 発話後のクールダウン |
| max_proactive_tokens | int | 256 | 発話最大トークン数 |
| user_cooldown_on_ignore | float | 300.0 | 無視時のクールダウン（秒） |
| trigger_weights | dict | see below | トリガー重み |
| speak_threshold | float | 0.60 | 発話開始閾値 |

**trigger_weights デフォルト**:
```yaml
trigger_weights:
  time: 0.25
  memory: 0.45
  context: 0.15
  mood: 0.15
```

## PersonalityConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| name | str | "Iris" | AIの名前 |
| thinking_mode_default | bool | False | デフォルト思考モード |
| mode_default | str | "auto" | 動作モード（auto/manual） |
| prompt_file | str | ".iris/config/personality_default.md" | システムプロンプトファイル |

## MemoryConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| episodic_path | str | ".iris/data/episodes.jsonl" | エピソード記憶ファイル |
| semantic_path | str | ".iris/data/semantic.jsonl" | 意味記憶ファイル |
| vector_db_path | str | ".iris/data/chroma_db" | ChromaDBディレクトリ |
| episodic_max_entries | int | 30 | エピソード記憶上限 |
| semantic_max_entries | int | 100 | 意味記憶上限 |
| rag_max_results | int | 3 | RAG検索最大件数 |
| agents_md_path | str | ".iris/data/iris_profile.md" | 構造記憶ファイル |
| agents_md_max_bytes | int | 2048 | 構造記憶最大サイズ |

## SessionConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| host | str | "127.0.0.1" | バインドアドレス |
| port | int | 9876 | TCPポート番号 |
| access_token | str | "" | アクセストークン（空文字 = 検証スキップ） |

## LoggingConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| file_level | str | "INFO" | ファイルログレベル |
| console_level | str | "" | コンソールログレベル（空=ファイルに準拠） |
| dir | str | "logs" | ログ出力ディレクトリ |
| max_bytes | int | 5242880 | ログファイル最大サイズ |
| backup_count | int | 14 | 保持する起動世代数 |

## config.yaml 例

```yaml
# シングルモード（モデル1つ、全処理に使用）
model:
  provider: openrouter
  base_url: https://openrouter.ai/api/v1
  api_key: "${OPENROUTER_API_KEY}"
  models:
    - name: google/gemma-4-26b-a4b-it:free
      roles: [default]
      max_tokens: 1024
  temperature: 0.7

# マルチモード（モデル複数、roleで使い分け）
# model:
#   provider: ollama
#   base_url: http://localhost:11434
#   models:
#     - name: qwen3.5:2b
#       roles: [default]
#       max_tokens: 512
#     - name: qwen3.5:9b
#       roles: [smart]
#       max_tokens: 1024
#   temperature: 0.7

proactive:
  enabled: false
  check_interval_sec: 5.0
  speak_threshold: 0.60
  trigger_weights:
    time: 0.25
    memory: 0.45
    context: 0.15
    mood: 0.15

session:
  host: 127.0.0.1
  port: 9876
  access_token: ""

logging:
  file_level: INFO
  console_level: ""
  dir: logs
  max_bytes: 5242880
  backup_count: 14
```
