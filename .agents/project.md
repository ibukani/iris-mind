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
Self-Modification Module (差分生成→承認→テスト→登録)  [保留中]
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
| `config.py` | 設定管理 | `Config.load()` → yaml → pydantic, `Config.model_names` プロパティ |
| `llm_bridge.py` | LLM抽象化 | `chat(model=...)`, `is_available()` |
| `personality.py` | キャラ管理 | `build_system_prompt()`, `build_thinking_prompt()` |
| `reflexion.py` | 内省ループ | `reflect()` → dict, `quick_reflect()` |
| `context.py` | 会話Compaction管理 | `ContextManager.check_and_summarize()`, `force_summarize()`, `build_compact_messages()` |
| `conversation.py` | 会話オーケストレーション | `ConversationService.process_input()` → ProcessResult |
| `tool_executor.py` | Tool Call実行共通基盤 | `ToolExecutionEngine.execute_all()`, `should_follow_up()` |
| `planner.py` | タスク分解 | `Planner.analyze()`, `is_complex()` |
| `executor.py` | サブタスク逐次実行 | `Executor.execute_plan()`（内部でToolExecutionEngine利用） |
| `commands.py` | コマンド処理 | `handle_command()` → `CommandResult` |
| `cli.py` | 薄いUI層 | `CliSession.run()`（会話ロジックはConversationService委譲） |

### memory/ — 記憶管理
| ファイル | 責務 | 公開API |
|----------|------|---------|
| `stores.py` | 3種の記憶ストア + Protocolインターフェース | `AgentsMdStore.load/update`, `EpisodicStore.add/get_recent`, `SemanticStore.add/search` |
| `vector_store.py` | ベクトルDB + BM25（スレッドセーフ） | `VectorStore.add/update/search/delete/count` |
| `persona_profile.py` | ペルソナ管理 | `PersonaProfile.get_speech_style()`, `get_traits()`, `update_from_reflection()` |
| `persona_data.py` | ペルソナデータ（専用JSON） | `PersonaData.add_entry()`, `get_top()`, `get_all()`, `clear()` |
| `data/iris_profile.md` | 構造記憶（2KB上限） | Iris自身の自己認識ファイル（話し方・性格は含まず） |

### capabilities/ — 機能モジュール
| モジュール | ツール | 説明 |
|-----------|--------|------|
| `file_ops/` | `read_file`, `write_file`, `list_files` | ファイル読み書き・一覧 |
| `code_exec/` | `run_python`, `run_shell` | 隔離サブプロセスでのコード実行 |
| `self_mod/` | `generate_capability`, `modify_file`, `sandbox_test` | 自己改変・差分適用・テスト（保留中、フロー未統合） |

### capabilities/registry.py — Capability Registry
- `Capability`: ツール定義（name, description, parameters, func）
- `CapabilityRegistry`: 登録・検索・実行・動的発見
- `discover_modules()`: `capabilities/*/server.py` を動的import
- 各server.pyは `register(registry)` 関数をエクスポートする契約

## データフロー

### 起動時
1. `Config.load()` → yaml読込（唯一のパース箇所）
2. Ollama再起動 + Configから指定モデルを確認・pull
3. `LLMBridge` → Ollama接続確認
4. `CapabilityRegistry.discover_modules()` → tool定義収集
5. `AgentsMdStore` → 構造記憶読込、`PersonaData` → ペルソナJSON読込
6. 直近のEpisodicStore, SemanticStoreを取得
7. メインループ開始

### 会話時（ConversationService 10フェーズ）
1. CliSession: ユーザー入力受付 → コマンド or ConversationServiceへ委譲
2. `_classify_scenario()`: 2段階分類（キーワード→LLM fallback）
3. `_resolve_model_params()`: モデル選択（副作用なし、model名を直接chatに渡す）
4. `check_and_summarize()`: コンテキスト圧縮判定
5. `_retrieve_rag()`: 意味記憶から関連教訓を検索（Plan/非Plan共通、1度だけ）
6. `_build_system_prompt()`: personality + 会話要約 + 構造記憶 + エピソード + RAGを統合
7. Plan判定: Planner.analyze() → is_complex
8. `_handle_plan()` or `_handle_direct_response()`: 応答生成
9. `_execute_tool_calls()`: Tool Call実行＋フォローアップ
10. `_run_quick_reflection()`: 定期Reflection（5メッセージごと）
11. CliSession: 応答表示
12. 終了時: Reflexion → エピソード保存 + 教訓抽出

## 設定（config.yaml）
```yaml
model:        # name, fast_model, base_url, max_tokens, max_tokens_fast, temperature, context_window, compaction_threshold
personality:  # name, mode_default
memory:       # paths, 各上限値, RAG設定
```

## 開発ワークフロー
1. 新機能は `capabilities/<name>/server.py` に追加
2. テストは `sandbox_test()` または `run_python` で実施
3. 変更はユーザー承認必須
4. 構造記憶 `memory/data/iris_profile.md` は変更時に更新

## .gitignore 対象
.venv/, __pycache__/, *.pyc, *.pyo, memory/chroma_db/, memory/*.jsonl, .DS_Store, *.log
