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
├── quasi_sync: QuasiSyncConfig — 準同期入力制御
├── session: SessionConfig      — セッション・通信
└── logging: LoggingConfig      — ログ出力
```

## ModelConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| models | list[ModelEntry] | qwen3.5:9b (default) | 使用モデル一覧 |
| default_temperature | float | 0.7 | LLM生成温度（各ModelEntryで未指定時のフォールバック） |
| default_num_ctx | int | 8192 | コンテキスト長（各ModelEntryで未指定時のフォールバック） |
| default_num_gpu | int | 99 | GPUレイヤー数（各ModelEntryで未指定時のフォールバック, Ollamaのみ） |
| default_context_window | int | 8192 | 圧縮トリガー閾値（各ModelEntryで未指定時のフォールバック） |

**ModelEntry**:

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| name | str | — | モデル名（Ollamaタグ形式 or OpenRouterモデルスラッグ） |
| roles | list[str] | ["default"] | このモデルが担うロール一覧 |
| provider | str | "ollama" | プロバイダ種別（"ollama" or "openrouter"） |
| base_url | str | "http://localhost:11434" | API URL（Ollama or OpenRouter） |
| api_key | str | "" | OpenRouter APIキー（${VAR_NAME}形式対応） |
| max_tokens | int | 512 | 最大出力トークン数 |
| temperature | float \| None | None | モデル個別の温度設定（上書き用） |
| num_ctx | int \| None | None | モデル個別のコンテキスト長（上書き用） |
| num_gpu | int \| None | None | モデル個別のGPUレイヤー数（Ollamaのみ） |
| main_gpu | int \| None | None | 使用するGPUデバイス番号（マルチGPU環境） |
| context_window | int \| None | None | モデル個別の圧縮トリガー閾値 |
| capabilities | list[str] \| None | None | モデルの機能ラベル（例: ["vision", "tools"]） |
| performance_tier | str | "balanced" | 性能区分（"fast" / "balanced" / "capable"） |
| tokenizer_repo_id | str | "" | HuggingFace Hub のリポジトリID（例: "Qwen/Qwen3.5-9B"） |
| tokenizer_local_path | str | "" | ローカル tokenizer.json のパス |
| tokenizer_hf_token | str | "" | gated repo用 HF Token（${VAR_NAME}形式対応） |

- `roles` は YAML上で1要素なら文字列でも記述可能: `roles: default`
- モデルが1つだけの場合はシングルモードとなり、全処理にそのモデルを使用
- 複数モデルがある場合は `get_model(role)` で role に合致するモデルを選択
- 各モデルが独立した `provider` / `base_url` / `api_key` を持つため、OllamaとOpenRouterの混在が可能
- 同じ `(provider, base_url, api_key)` のモデルは1つの Provider インスタンスを共有
- `temperature` / `num_ctx` / `num_gpu` / `context_window` が `None` の場合は `default_*` が使用される

**Tokenizer解決順**:
1. `tokenizer_local_path` → ローカルファイルから直接ロード
2. `tokenizer_repo_id` → HuggingFace Hub から `from_pretrained`（`tokenizer_hf_token` で gated repo対応）
3. フォールバック → `len(text) // 2` によるNaive推定

**ModelConfig ヘルパーメソッド**:

| メソッド | 戻り値 | 説明 |
|---------|--------|------|
| `model_names` | list[str] | 全モデル名一覧（property） |
| `get_model(role)` | str | 指定 role に合致するモデル名。未合致時は models[0] にフォールバック |
| `get_effective_temperature(role)` | float | role 別実効温度。モデル個別設定がなければ `default_temperature` |
| `get_effective_num_ctx(role)` | int | role 別実効コンテキスト長。モデル個別設定がなければ `default_num_ctx` |
| `get_effective_num_gpu(role)` | int | role 別実効GPUレイヤー数。モデル個別設定がなければ `default_num_gpu` |
| `get_effective_context_window(role)` | int | role 別実効圧縮閾値。モデル個別設定がなければ `default_context_window` |
| `get_model_capabilities(role)` | list[str] | role 別の機能ラベル一覧 |
| `get_model_performance_tier(role)` | str | role 別の性能区分 |

## ProactiveConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| check_interval_sec | float | 5.0 | TimerTick 間隔（秒） |
| min_interval_sec | float | 30.0 | 自発発話の最小間隔 |
| max_interval_sec | float | 300.0 | 自発発話の最大間隔（時間スコア飽和） |
| trigger_weights | dict | see below | トリガー重み |
| speak_threshold | float | 0.60 | 発話開始閾値 |
| abbreviated_threshold | float | 0.25 | 短縮発話のスコア閾値 |

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
| prompt_file | str | ".iris/config/personality_default.md" | システムプロンプトファイル |

## MemoryConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| episodic_path | str | ".iris/data/episodes.jsonl" | エピソード記憶ファイル |
| semantic_path | str | ".iris/data/semantic.jsonl" | 意味記憶ファイル |
| vector_db_path | str | ".iris/data/chroma_db" | ChromaDBディレクトリ |
| episodic_max_entries | int | 30 | エピソード記憶上限 |
| semantic_max_entries | int | 100 | 意味記憶上限 |
| agents_md_path | str | ".iris/data/iris_profile.md" | 構造記憶ファイル |
| agents_md_max_bytes | int | 2048 | 構造記憶最大サイズ |

## QuasiSyncConfig

準同期入力（キー入力の断片が連続して届く状態）を制御する。

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| response_readiness | ResponseReadinessConfig | default | 応答準備判定の設定 |

### ResponseReadinessConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| tier1_min_fragments | int | 2 | Tier1発火に必要な最小断片数 |
| tier1_question_detect | bool | True | 疑問文検出の有効/無効 |
| confidence_threshold | float | 0.6 | 応答準備完了の信頼度閾値 |
| llm_model_role | str | "fast" | 応答準備判定に使うモデルロール |

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
# シングルモード（Ollama 1モデル）
model:
    default_num_ctx: 8192
    default_context_window: 8192
    default_temperature: 0.7
    models:
        - name: qwen3.5:9b
          roles: [default]
          provider: ollama
          base_url: http://localhost:11434
          max_tokens: 1024
          tokenizer_repo_id: Qwen/Qwen3.5-9B

# マルチプロバイダモード（Ollama + OpenRouter 混在）
# model:
#     default_num_ctx: 8192
#     default_context_window: 8192
#     default_num_gpu: 99
#     default_temperature: 0.7
#     models:
#         - name: qwen3.5:9b
#           roles: [default, fast]
#           provider: ollama
#           base_url: http://localhost:11434
#           max_tokens: 1024
#
#         - name: gpt-4o
#           roles: [capable]
#           provider: openrouter
#           base_url: https://openrouter.ai/api/v1
#           api_key: ${OPENROUTER_API_KEY}
#           max_tokens: 4096
#           context_window: 128000
#           tokenizer_repo_id: Xenova/gpt-4o

proactive:
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
