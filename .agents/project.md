# Iris v0.2 — ヘキサゴナルアーキテクチャ + 自律会話機能

## コンセプト
自律的に行動・進化できるAIアシスタント「Iris」の開発。
Neuro-samaにインスパイアされた、知的で親しみやすいキャラクター。
ローカルLLM（Ollama + Qwen3.5）またはOpenRouter上で動作し、Reflexionループによる自己改善と
Capability Registryによる動的機能拡張を特徴とする。

## バージョン目標
- v0.1.0: 基本会話 + Capability拡張（**完了**）
- v0.2.0: ヘキサゴナルリファクタリング + 自律的会話（ProactiveEngine）（**完了**）

## アーキテクチャ

```
adapters/            (UI層 — CLI / API / GUI)
    ↕  KernelContext（組み立て済みコンポーネント）
iris/kernel/         (ビジネスロジック — UI非依存)
├── factory          (KernelFactory — 依存構築, composition root)
├── agent_kernel     (状態管理・異常検知・イベント統括)
├── event_bus        (インメモリ同期EventBus)
├── proactive        (自発発話エンジン)
├── conversation     (会話オーケストレーション)
├── reflexion        (自己反省)
├── context          (会話履歴compaction)
└── tool_executor    (Tool Call実行)
    ↕
iris/llm/            (外部サービス通信 — Ollama / OpenRouter)
iris/memory/         (記憶管理 — Episodic/Semantic/Persona)
iris/capabilities/   (機能拡張 — file_ops/code_exec/self_mod)
iris/personality/    (システムプロンプト管理)
```

KernelContext に集約され、Adapter は KernelContext オブジェクトから必要なコンポーネントにアクセスする。

## 設計原則

### 依存方向
```
adapters → iris/kernel → iris/llm / iris/memory / iris/capabilities
```
- `adapters/` は `iris/kernel/` に依存するが、逆はない
- `iris/kernel/` はインフラ層を抽象化されたPort経由で利用
- **循環import禁止**

### ガバナンスモデル（自律発話）
| Tier | 方式 | 例 |
|------|------|-----|
| Tier 1 | ルールベース自動許可 | 挨拶・定型確認 |
| Tier 2 | LLM自己判断 | 話題提案・気遣い |
| Tier 3 | AgentKernel介入 | 異常検知・過剰発話抑制 |

### 状態管理
AgentState (IDLE / PROCESSING / PROACTIVE / REFLECTING / THINKING / SLEEPING) で
イベント駆動の状態遷移を一元管理。

## フォルダ構成

```
my-iris/
├── .iris/                       # 設定・データファイル
│   ├── config/
│   │   └── personality_default.md
│   └── data/
│       ├── iris_profile.md
│       ├── episodes.jsonl
│       ├── semantic.jsonl
│       ├── persona_data.json
│       └── chroma_db/
├── adapters/                    # UI層
│   ├── __init__.py
│   └── cli/
│       ├── __init__.py
│       └── server.py
├── iris/                        # アプリケーションコア
│   ├── __init__.py
│   ├── kernel/
│   │   ├── __init__.py
│   │   ├── agent_kernel.py
│   │   ├── agent_state.py
│   │   ├── config.py
│   │   ├── context.py
│   │   ├── conversation.py
│   │   ├── event_bus.py
│   │   ├── factory.py          ← KernelFactory / KernelContext
│   │   ├── memory_manager.py
│   │   ├── proactive.py
│   │   ├── reflexion.py
│   │   └── tool_executor.py
│   ├── personality/
│   │   ├── __init__.py
│   │   └── personality.py
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── stores.py
│   │   ├── vector_store.py
│   │   ├── persona_data.py
│   │   └── persona_profile.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── llm_bridge.py
│   │   ├── provider.py
│   │   ├── ollama_provider.py
│   │   └── openrouter_provider.py
│   ├── capabilities/
│   │   ├── __init__.py
│   │   ├── registry.py
│   │   ├── file_ops/server.py
│   │   ├── code_exec/server.py
│   │   └── self_mod/server.py
│   └── commands/
│       ├── __init__.py
│       └── handler.py
├── config.yaml
├── pyproject.toml
├── docs/
├── .agents/
│   ├── project.md
│   ├── context.md
│   └── tasks.md
├── AGENTS.md
└── main.py
```

## 開発ワークフロー
1. 機能追加は `iris/capabilities/<name>/server.py` に配置
2. `register(registry: CapabilityRegistry)` 関数をエクスポート
3. `@registry.register_func(...)` デコレータでツール定義
4. `__init__.py` を各パッケージに配置（必須）
5. テストは `ruff check . && mypy .` で品質確認
6. 変更はユーザー承認必須（差分表示 → 承認 → 適用）
7. 構造記憶 `.iris/data/iris_profile.md` はcapability追加時に更新
8. ドキュメント更新はコード変更と同一コミットに必須
