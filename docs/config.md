# Config 設計仕様

## 概要

Iris v0.2 の設定は Pydantic BaseModel で構成される。`config.yaml` から読み込み、型バリデーションを自動実行する。

## Config ツリー

```
Config
├── model: ModelConfig          — LLMモデル関連
├── personality: PersonalityConfig — 人格・プロンプト
├── memory: MemoryConfig        — 記憶管理
└── proactive: ProactiveConfig  — 自発発話
```

## ModelConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| models | list[ModelEntry] | qwen3.5:2b (base), qwen3.5:9b (smart) | 使用モデル一覧 |
| provider | str | "ollama" | プロバイダ種別（"ollama" or "openrouter"） |
| base_url | str | "http://localhost:11434" | API URL（Ollama or OpenRouter） |
| api_key | str | "" | OpenRouter APIキー（${VAR_NAME}形式対応） |
| temperature | float | 0.7 | LLM生成温度 |
| num_gpu | int | 0 | GPUレイヤー数（0=CPU、Ollamaのみ） |
| num_ctx | int | 8192 | コンテキスト長 |
| context_window | int | 0 | 会話ウィンドウサイズ（0=無制限） |
| compaction_threshold | float | 0.85 | 要約発動閾値（比率） |

**ModelEntry**:

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| name | str | — | モデル名（Ollamaタグ形式 or OpenRouterモデルスラッグ） |
| role | str | "base" | "base" または "smart" |
| max_tokens | int | 512 | 最大出力トークン数 |

**EscalationConfig**:

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| enabled | bool | True | エスカレーション有効 |
| max_retries | int | 1 | 最大リトライ回数 |
| swap_on_escalate | bool | True | エスカレーション時にモデル切替 |
| keep_alive_duration | str | "5m" | モデル維持時間 |

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
| prompt_file | str | "memory/personality_default.md" | システムプロンプトファイル |

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

## config.yaml 例

```yaml
model:
  provider: ollama                    # "ollama" or "openrouter"
  base_url: http://localhost:11434    # Ollama: localhost:11434 / OpenRouter: https://openrouter.ai/api/v1
  api_key: "${OPENROUTER_API_KEY}"    # OpenRouter利用時のみ
  models:
    - name: qwen3.5:2b
      role: base
      max_tokens: 512
    - name: qwen3.5:9b
      role: smart
      max_tokens: 1024
  temperature: 0.7

proactive:
  enabled: false
  check_interval_sec: 5.0
  speak_threshold: 0.60
  trigger_weights:
    time: 0.25
    memory: 0.45
    context: 0.15
    mood: 0.15
```
