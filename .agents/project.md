# Iris v0.2 — アーキテクチャリファクタリング + 自律会話機能

## コンセプト
自律的に行動・進化できるAIアシスタント「Iris」の開発。
Neuro-samaにインスパイアされた、知的で親しみやすいキャラクター。
ローカルLLM（Ollama + Qwen3.5）上で動作し、Reflexionループによる自己改善と
Capability Registryによる動的機能拡張を特徴とする。

## バージョン目標
- v0.1.0: 基本会話 + Capability拡張（**完了**）
- v0.2.0: ヘキサゴナルリファクタリング + 自律的会話（ProactiveEngine）

## アーキテクチャ

```
adapters/            (UI層 — CLI / API / GUI)
    ↕  イベント駆動（EventBus）
kernel/              (ビジネスロジック — UI非依存)
├── agent_kernel     (状態管理・異常検知・イベント統括)
├── event_bus        (インメモリ同期EventBus)
├── proactive        (自発発話エンジン)
├── conversation     (会話オーケストレーション)
├── planner          (タスク分解)
├── executor         (サブタスク実行)
└── reflexion        (自己反省)
    ↕
personality/         (人格・プロンプト管理)
    ↕
memory/              (記憶管理 — Episodic/Semantic/Persona)
    ↕
llm/                 (外部サービス通信 — Ollama)
    ↕
capabilities/        (機能拡張 — file_ops/code_exec/self_mod)
```

## 設計原則

### 依存方向
```
adapters → kernel → llm / memory / capabilities
```
- `adapters/` は `kernel/` に依存するが、逆はない
- `kernel/` はインフラ層を抽象化されたPort経由で利用
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
├── iris/                       # メインパッケージ
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── constants.py
│   ├── kernel/
│   │   ├── __init__.py
│   │   ├── agent_kernel.py
│   │   ├── event_bus.py
│   │   ├── proactive.py
│   │   ├── conversation.py
│   │   ├── planner.py
│   │   ├── executor.py
│   │   └── reflexion.py
│   ├── personality/
│   │   ├── __init__.py
│   │   ├── personality.py
│   │   └── persona_data.py
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── stores.py
│   │   ├── vector_store.py
│   │   ├── persona_profile.py
│   │   └── data/
│   ├── llm/
│   │   ├── __init__.py
│   │   └── llm_bridge.py
│   ├── capabilities/
│   │   ├── __init__.py
│   │   ├── registry.py
│   │   ├── file_ops/
│   │   ├── code_exec/
│   │   └── self_mod/
│   └── commands/
│       ├── __init__.py
│       └── commands.py
├── adapters/                   # UI層
│   ├── __init__.py
│   ├── cli.py
│   ├── api.py                  # 将来用
│   └── gui.py                  # 将来用
├── config.yaml
├── pyproject.toml
├── tests/
├── docs/
├── memory/
│   └── data/iris_profile.md
├── .agents/
│   ├── project.md
│   ├── context.md
│   └── tasks.md
├── AGENTS.md
└── main.py
```

## 開発ワークフロー
1. 機能追加は `iris/capabilities/<name>/server.py` に配置
2. テストは FakeLLM + InMemoryStore で自動化
3. 変更はユーザー承認必須（差分表示 → 承認 → 適用）
4. 構造記憶 `memory/data/iris_profile.md` はcapability追加時に更新
5. ドキュメント更新はコード変更と同一コミットに必須
