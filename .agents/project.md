# Iris v0.3 — 3-Process Architecture + Documentation-First

## コンセプト
自律的に行動・進化できるAIアシスタント「Iris」の開発。
Neuro-samaにインスパイアされた、知的で親しみやすいキャラクター。
ローカルLLM（Ollama + Qwen3.5）またはOpenRouter上で動作し、Reflexionループによる自己改善と
Capability Registryによる動的機能拡張を特徴とする。

## バージョン目標
- v0.1.0: 基本会話 + Capability拡張（**完了**）
- v0.2.0: ヘキサゴナルリファクタリング + 自律的会話（ProactiveEngine）（**完了**）
- v0.3.0: 3-Process分解（Input / Kernel / Output）+ マルチ入力対応（**進行中**）

## 現在のブランチ
- `main`

## アーキテクチャ (v0.3)

```
Controller Process (起動・監視)
        │
        ├── Input Process (CLI, API...)
        │       │ Named Pipe
        ├── Kernel Process (EventBus, AgentKernel, Conversation, Proactive, Memory, LLM...)
        │       │ Named Pipe
        └── Output Process (CLI, GUI...)
```

Kernel が中心的な状態を持ち、Input / Output は stateless。
詳細は `docs/adr/001-3-process-architecture.md` および `docs/architecture.md` を参照。

## 設計原則

### 依存方向 (v0.2から継続)
```
debug_tools/ → iris/kernel → iris/llm / iris/memory / iris/capabilities
(UI層)         (ドメイン層)     (インフラ層)
```

### ガバナンスモデル（自律発話, v0.2から継続）
| Tier | 方式 | 例 |
|------|------|-----|
| Tier 1 | ルールベース自動許可 | 挨拶・定型確認 |
| Tier 2 | LLM自己判断 | 話題提案・気遣い |
| Tier 3 | AgentKernel介入 | 異常検知・過剰発話抑制 |

### Documentation-First
設計変更時はコード実装前に設計文書を作成する。
- Architecture Decision Records を `docs/adr/` に保存
- 決定内容は `.agents/context.md` にも追跡

## フォルダ構成 (v0.3現在)

```
iris-kernel/
├── .iris/                       # 設定・データファイル
├── debug_tools/                 # 入出力分離のデバッグ用ツール群
│   ├── __init__.py
│   ├── cli/
│   │   ├── input_main.py        # Input Process
│   │   ├── output_main.py       # Output Process
│   │   ├── renderer.py          # 表示ロジック
│   │   └── server.py            # 単一プロセス互換用
│   ├── tcp_input/
│   │   └── main.py              # TCP Input アダプター
├── iris/                        # アプリケーションコア
│   ├── kernel/                  # Kernel Process
│   │   ├── agent_kernel.py
│   │   ├── agent_state.py
│   │   ├── config.py
│   │   ├── context.py
│   │   ├── kernel_process.py    # KernelProcess
│   │   ├── conversation.py
│   │   ├── event.py             # イベントクラス群
│   │   ├── event_bus.py         # EventBusProtocol + EventBus
│   │   ├── factory.py           # KernelFactory
│   │   ├── io/
│   │   │   ├── models.py
│   │   │   ├── protocols.py
│   │   │   ├── input_manager.py
│   │   │   └── output_manager.py
│   │   ├── ipc/
│   │   │   ├── __init__.py
│   │   │   └── transport.py
│   │   ├── llm_pipeline.py      # LLMPipeline
│   │   ├── logging.py           # ログ設定
│   │   ├── memory_manager.py
│   │   ├── proactive.py
│   │   ├── reflexion.py
│   │   ├── reflexion_manager.py
│   │   ├── tool_executor.py
│   │   └── context.py           # ContextManager
│   ├── llm/
│   ├── memory/
│   ├── capabilities/
│   │   └── io/                  # I/O drivers
│   ├── commands/
│   └── personality/
├── docs/
│   ├── adr/
│   │   └── 001-3-process-architecture.md
│   ├── architecture.md
│   ├── ipc-spec.md
│   └── ... (既存設計書)
├── main.py
└── config.yaml
```

## 開発ワークフロー
1. 設計変更は `docs/adr/` に記録（Documentation-First）
2. コード実装前に設計文書をレビュー承認
3. 機能追加は `iris/capabilities/<name>/server.py` に配置
4. テストは `ruff check . && mypy . && pytest tests/` で品質確認
5. 変更はユーザー承認必須（差分表示 → 承認 → 適用）
6. コード変更とドキュメント更新は同一コミットに必須
