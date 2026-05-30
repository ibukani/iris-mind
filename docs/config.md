# Config 設計仕様

## 概要

Iris の設定は Pydantic BaseModel で構成される。`config.yaml` から読み込み、型バリデーションを自動実行する。

## Config ツリー

```
Config
├── model: ModelConfig          — LLMモデル関連
├── personality: PersonalityConfig — 人格・プロンプト
├── account: AccountConfig      — アカウント管理
├── memory: MemoryConfig        — 記憶管理
├── proactive: ProactiveConfig  — 自発発話
├── inhibition: InhibitionConfig — 抑制制御
├── quasi_sync: QuasiSyncConfig — 準同期入力制御
├── session: SessionConfig      — セッション・通信
├── timer: TimerConfig          — 鼓動タイマー
├── logging: LoggingConfig      — ログ出力
├── debug: DebugConfig          — デバッグ・トレース
└── plugins: PluginConfig       — プラグイン管理
```

## ModelConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| providers | dict[str, ProviderConnection] | {} | プロバイダ接続設定（base_url / api_key） |
| hf_token | str | "" | HuggingFace gated repo 用トークン（全モデル共通） |
| models | list[ModelEntry] | qwen3.5:4b (default) | 使用モデル一覧（config.yaml に定義） |
| default_temperature | float | 0.85 | LLM生成温度（各ModelEntryで未指定時のフォールバック） |
| default_num_ctx | int | 8192 | コンテキスト長（各ModelEntryで未指定時のフォールバック） |
| default_num_gpu | int | 99 | GPUレイヤー数（各ModelEntryで未指定時のフォールバック, Ollamaのみ） |
| default_context_window | int | 8192 | 圧縮トリガー閾値（各ModelEntryで未指定時のフォールバック） |

### ProviderConnection

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| base_url | str | "" | API URL（未設定時はプロバイダ別ハードコードデフォルト） |
| api_key | str | "" | APIキー（${VAR_NAME}形式対応） |

**ModelEntry**:

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| name | str | — | モデル名（Ollamaタグ形式 or OpenRouterモデルスラッグ） |
| roles | list[str] | ["default"] | このモデルが担うロール一覧 |
| provider | str | "ollama" | プロバイダ種別（"ollama" / "openrouter" / "google"）。`providers` のキーとしても使用 |
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
| keep_alive | str \| None | None | モデル維持時間（Ollama, 例: "5m"） |
| presence_penalty | float \| None | None | 新規話題へのペナルティ |
| frequency_penalty | float \| None | None | 頻出トークンへのペナルティ |
| repeat_penalty | float \| None | None | 繰り返しトークンへのペナルティ（Ollama） |
| reasoning | bool | False | Ollama の reasoning/thinking モード有効/無効。`show_thinking=True` の Plan で上書き可能 |

- `roles` は YAML上で1要素なら文字列でも記述可能: `roles: default`
- モデルが1つだけの場合はシングルモードとなり、全処理にそのモデルを使用
- 複数モデルがある場合は `get_model(role)` で role に合致するモデルを選択
- 各モデルは `provider` で参照するプロバイダを指定。接続情報（`base_url` / `api_key`）は `model.providers` に集約
- モデル個別の `base_url` / `api_key` は持たない。プロバイダ内で全モデルが同一接続を共有
- 各プロバイダインスタンスは `(provider, base_url, api_key)` でユニーク化され、同一接続のモデル間で共有される
- `temperature` / `num_ctx` / `num_gpu` / `context_window` が `None` の場合は `default_*` が使用される
- `reasoning` は `show_thinking=True` の Plan（タスク応答時）で上書きされる。雑談や abbreviated 応答では自動的に `reasoning=False` となる

**Tokenizer解決順**:
1. `tokenizer_local_path` → ローカルファイルから直接ロード
2. `tokenizer_repo_id` → HuggingFace Hub から `from_pretrained`（`model.hf_token` で gated repo対応）
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
| `get_effective_max_tokens(role)` | int | role 別最大トークン数。モデル設定がなければ 4096 |
| `get_model_capabilities(role)` | list[str] | role 別の機能ラベル一覧 |
| `get_model_performance_tier(role)` | str | role 別の性能区分 |

## ProactiveConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| check_interval_sec | float | 5.0 | TimerTick 間隔（秒） |
| min_interval_sec | float | 30.0 | 自発発話の最小間隔 |
| active_min_interval_sec | float | 2.0 | アクティブ時の最小間隔 |
| max_interval_sec | float | 300.0 | 自発発話の最大間隔（時間スコア飽和） |
| trigger_weights | dict | see below | トリガー重み |
| speak_threshold | float | 0.30 | 発話開始閾値 |
| abbreviated_threshold | float | 0.25 | 短縮応答切り替え閾値 |

**trigger_weights デフォルト**:
```yaml
trigger_weights:
  time: 0.40
  memory: 0.35
  context: 0.15
```

## PersonalityConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| name | str | "Iris" | AIの名前 |
| prompt_file | str | ".iris/config/system_prompt.md" | システムプロンプトファイル |
| node_prompts_dir | str | ".iris/config/node_prompts" | ノード別プロンプト格納ディレクトリ |

## AccountConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| accounts_path | str | ".iris/data/accounts.jsonl" | アカウント情報ファイル |
| identities_path | str | ".iris/data/account_identities.jsonl" | 外部ID紐付け情報ファイル |
| bindings_path | str | ".iris/data/account_bindings.jsonl" | セッション紐付けファイル |

## InhibitionConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| post_execution_cooldown_sec | float | 5.0 | 実行後クールダウン（秒） |
| max_concurrent_executions | int | 1 | 同時実行数上限 |
| inhibit_proactive_during_execution | bool | True | 実行中はproactive抑制 |
| inhibit_proactive_during_cooldown | bool | True | クールダウン中はproactive抑制 |
| tts_mora_per_sec | float | 6.5 | TTSモーラ/秒（発話時間推定用） |

## MemoryConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| episodic_path | str | ".iris/data/episodes.jsonl" | エピソード記憶ファイル |
| semantic_path | str | ".iris/data/semantic.jsonl" | 意味記憶ファイル |
| vector_db_path | str | ".iris/data/chroma_db" | ChromaDBディレクトリ |
| episodic_max_entries | int | 30 | エピソード記憶上限 |
| semantic_max_entries | int | 100 | 意味記憶上限 |
| agents_md_path | str | ".iris/config/iris_profile.md" | 構造記憶ファイル |
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
| llm_model_role | str | "low" | 応答準備判定に使うモデルロール |

## TimerConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| interval_sec | float | 5.0 | 鼓動タイマーの発行間隔（秒） |

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
| loggers | dict[str, str] | {} | ロガー別レベル設定（例: {"iris.kernel": "DEBUG"}） |
| console_format | str | "" | コンソールログフォーマット（空文字=デフォルト） |

## DebugConfig

デバッグ・トレース機能の設定。

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| enabled | bool | False | デバッグ機能の有効/無効 |
| trace_max_entries | int | 500 | EventTracer リングバッファ最大数 |
| capture_enabled | bool | False | DebugCapture の有効/無効（`/debug on/off` で切替可） |
| capture_auto_dump | bool | False | キャプチャを自動で `logs/debug/` にファイル保存 |
| capture_max_entries | int | 10 | DebugCapture の保持上限 |

## PluginConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| paths | list[str] | ["iris/"] | プラグイン探索パス |
| disabled | list[str] | [] | 無効化するプラグイン名一覧 |
| config | dict[str, dict] | {} | プラグイン別設定 |

## config.yaml 例

```yaml
# シングルモード（Ollama 1モデル）
personality:
  name: Iris
  prompt_file: .iris/config/system_prompt.md

memory:
  agents_md_max_bytes: 2048
  agents_md_path: .iris/config/iris_profile.md
  episodic_max_entries: 30
  episodic_path: .iris/data/episodes.jsonl
  semantic_max_entries: 100
  semantic_path: .iris/data/semantic.jsonl
  vector_db_path: .iris/data/chroma_db

account:
  accounts_path: .iris/data/accounts.jsonl
  identities_path: .iris/data/account_identities.jsonl
  bindings_path: .iris/data/account_bindings.jsonl

proactive:
  check_interval_sec: 5.0
  min_interval_sec: 30.0
  active_min_interval_sec: 2.0
  max_interval_sec: 300.0
  trigger_weights:
    time: 0.40
    memory: 0.35
    context: 0.15
  speak_threshold: 0.30
  abbreviated_threshold: 0.25

model:
  providers:
    ollama:
      base_url: http://localhost:11434
    openrouter:
      base_url: https://openrouter.ai/api/v1
      api_key: ${OPENROUTER_API_KEY}
    google:
      base_url: https://generativelanguage.googleapis.com/v1beta/openai
      api_key: ${GEMINI_API_KEY}

  default_context_window: 8192
  default_num_ctx: 8192
  default_num_gpu: 99
  default_temperature: 0.85

  models:
    - name: qwen3.5:4b
      roles: default
      provider: ollama
      max_tokens: 1024
      reasoning: false
      tokenizer_repo_id: Qwen/Qwen3.5-4B

session:
  host: 127.0.0.1
  port: 9876

quasi_sync:
  response_readiness:
    confidence_threshold: 0.6
    llm_model_role: low
    tier1_min_fragments: 2
    tier1_question_detect: true

debug:
  enabled: false
  trace_max_entries: 500
  capture_enabled: false
  capture_auto_dump: false
  capture_max_entries: 10

timer:
  interval_sec: 5.0

logging:
  backup_count: 14
  console_format: "{time:YYYY-MM-DD HH:mm:ss} [{level}] {message}"
  console_level: DEBUG
  dir: logs
  file_level: INFO
  loggers:
    iris.io: DEBUG
  max_bytes: 5242880
```
