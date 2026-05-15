# Iris v0.3 — 3-Process Architecture + Documentation-First

## コンセプト
自律的に行動・進化できるAIアシスタント「Iris」の開発。
Neuro-samaにインスパイアされた、知的で親しみやすいキャラクター。
ローカルLLM（Ollama + Qwen3.5）またはOpenRouter上で動作し、Reflexionループによる自己改善と
Capability Registryによる動的機能拡張を特徴とする。

## バージョン目標
- v0.1.0: 基本会話 + Capability拡張（**完了**）
- v0.2.0: ヘキサゴナルリファクタリング + 自律的会話（ProactiveEngine）（**完了**）
- v0.3.0: Kernel-only プロジェクト化（Named Pipe IPC + Supervisor 管理コンソール）（**完了**）

## 現在のブランチ
- `main`

## アーキテクチャ (v0.3)

このリポジトリは Iris Kernel 本体のみを提供する。UI 層（CLI 等）は別プロジェクトが担当する。
Kernel は Named Pipe の Listener（サーバー）として起動し、外部 Client の接続を待つ。
詳細は `docs/architecture.md` を参照。

## 設計原則

### 依存方向 (v0.2から継続)
```
debug_tools/ → iris/kernel → iris/llm / iris/memory / iris/capabilities
(デバッグ用)  (ドメイン層)     (インフラ層)
```

### アーキテクチャ
```
Supervisor (main.py)
  ├── 管理コンソール (stdin) — /status, /shutdown
  └── KernelProcess
       ├── Named Pipe Listener (入力) — 外部プロセスから制御
       ├── Named Pipe Listener (出力) — 外部プロセスに出力
       └── iris/kernel/ — ドメイン層
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

## フォルダ構成 (v0.3 Kernel-only)

```
iris-kernel/
├── .iris/                       # 設定・データファイル
├── debug_tools/                 # デバッグ用ツール
│   └── tcp_input/
│       └── main.py              # TCP Input アダプター
├── iris/                        # アプリケーションコア
│   ├── kernel/                  # Kernel Process
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── agent_state.py
│   │   ├── logging.py
│   │   ├── core/                # コア（agent_kernel, kernel_process, factory）
│   │   ├── event/               # 内部イベント（event.py, event_bus.py）
│   │   ├── io/                  # I/O Manager（models, input_manager, output_manager）
│   │   └── services/            # ビジネスロジック（conversation, llm_pipeline,
│   │                              tool_executor, proactive, reflexion, 他）
│   ├── llm/
│   ├── memory/
│   ├── capabilities/            # ツール実装（@tool デコレータ + ToolRegistry）
│   │   ├── __init__.py
│   │   ├── registry.py
│   │   ├── file_ops/server.py
│   │   ├── code_exec/server.py
│   │   └── self_mod/server.py
│   ├── tools/                   # 型安全ツール基盤（@tool, ToolDef, ToolRegistry）
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── decorator.py
│   │   ├── registry.py
│   │   └── builtins/
│   │       └── output.py
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
