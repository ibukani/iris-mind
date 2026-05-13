# Iris プロジェクト概要

## コンセプト
自律的に行動・進化できるAIアシスタント「Iris」の開発。Neuro-samaに影響を受けた、知的で少しズレたキャラクター。ローカルLLM（Ollama + Qwen3.5）上で動作し、Reflexionループによる自己改善とCapability Registryによる動的機能拡張を特徴とする。

## アーキテクチャ

```
Personality Layer (思考モード切替)
       │
Conversation Manager (短期記憶 + 長期記憶)
       │
Context Manager (会話Compaction・Prune管理)
       │
Task Engine (Simple ReAct / Complex Plan-then-Execute)
       │
Capability Registry (MCPベースのツール管理)
       │
Outer Loop — Reflexion (セッション終了時の内省・教訓抽出)
       │
Self-Modification Module (差分生成→承認→テスト→登録)
```

## 思考モード
| モード | 用途 | 挙動 |
|--------|------|------|
| OFF | 日常会話・雑談 | 即レス、キャラ全開、軽快 |
| ON | ツール呼び出し・コード生成・エラー復帰 | ステップバイステップ推論 |

## モジュール一覧

### core/ — エンジン本体
| ファイル | 責務 | 公開API |
|----------|------|---------|
| `config.py` | 設定管理 | `Config.load()` → yaml → pydantic |
| `llm_bridge.py` | LLM抽象化 | `chat()`, `set_model()`, `is_available()` |
| `personality.py` | キャラ管理 | `build_system_prompt()`, `build_thinking_prompt()` |
| `reflexion.py` | 内省ループ | `reflect()` → dict(summary, lesson, missing_capability...) |
| `context.py` | 会話Compaction管理 | `ContextManager.check_and_summarize()`, `force_summarize()`, `build_compact_messages()` |

### memory/ — 記憶管理
| ファイル | 責務 | 公開API |
|----------|------|---------|
| `stores.py` | 3種の記憶ストア | `AgentsMdStore.load/update`, `EpisodicStore.add/get_recent`, `SemanticStore.add/search` |
| `vector_store.py` | ベクトルDB + BM25 | `VectorStore.add/update/search/delete/count` |
| `iris_profile.md` | 構造記憶（2KB上限） | Iris自身の自己認識ファイル |

### capabilities/ — 機能モジュール
| モジュール | ツール | 説明 |
|-----------|--------|------|
| `file_ops/` | `read_file`, `write_file`, `list_files` | ファイル読み書き・一覧 |
| `code_exec/` | `run_python`, `run_shell` | 隔離サブプロセスでのコード実行 |
| `self_mod/` | `generate_capability`, `modify_file`, `sandbox_test` | 自己改変・差分適用・テスト |

### capabilities/registry.py — Capability Registry
- `Capability`: ツール定義（name, description, parameters, func）
- `CapabilityRegistry`: 登録・検索・実行・動的発見
- `discover_modules()`: `capabilities/*/server.py` を動的import
- 各server.pyは `register(registry)` 関数をエクスポートする契約

## データフロー

### 起動時
1. `Config.load()` → yaml読込
2. `LLMBridge` → Ollama接続確認
3. `CapabilityRegistry.discover_modules()` → tool定義収集
4. `AgentsMdStore` → 構造記憶読込
5. 直近のEpisodicStore, SemanticStoreを取得
6. メインループ開始

### 会話時
1. ユーザー入力 → コマンド処理 or LLMへ送信
2. コンテキスト要約判定: compaction_threshold超過時はContextManagerが自動要約（fast_model使用）
3. システムプロンプト = personality + 会話要約 + 構造記憶 + 最近のepisode + 関連lesson(RAG)
4. LLM応答 → tool_callがあれば実行 → 結果を再送 → 最終応答表示
5. 終了時: Reflexion → エピソード保存 + 教訓抽出

## 設定（config.yaml）
```yaml
model:        # name, fast_model, base_url, max_tokens, max_tokens_fast, temperature, context_window, compaction_threshold
personality:  # name, thinking_mode_default
memory:       # paths, 各上限値, RAG設定
```

## 開発ワークフロー
1. 新機能は `capabilities/<name>/server.py` に追加
2. テストは `sandbox_test()` または `run_python` で実施
3. 変更はユーザー承認必須
4. 構造記憶 `memory/iris_profile.md` は変更時に更新

## .gitignore 対象
.venv/, __pycache__/, *.pyc, *.pyo, memory/chroma_db/, memory/*.jsonl, .DS_Store, *.log
